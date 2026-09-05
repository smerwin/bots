"""The gas huffer hunts by the probe scanner's `Group` column, and declines
what it cannot identify.

Issue #460, under #456. `ProbeScanResult.cellsTexts` is keyed by the header text
of the column a cell sits under, so `Dict.get "Group"` needed no parser change
-- the whole of this change is a rule, a fallback, and a status line that says
why nothing is being hunted.

**A missing `Group` column is not a match, and that is the emphasis.**
`Dict.get` answering `Nothing` is the reading saying it *cannot tell* what a row
is, which is not the same fact as a cell that reads something else, and
collapsing them in the permissive direction warps this ship into a site nobody
has identified. In a wormhole that is the expensive direction. So the rule
declines, and -- because a bot that declines silently is indistinguishable from
one with nothing to do -- the status line names the column, counts the rows and
tells that state apart from "this wormhole holds no gas site". Those want
different fixes from the operator: one is a scanner column they never made
visible, the other is a filter naming a group that is not here.

**`anomaly-group` and `anomaly-name` are independent conditions.**
`anomalyVerdict` asks them as two entries in one list, neither reading the
other's cell, so if both are set both must hold. The cases below ask for the
cross: a row matching Group but not a set Name is declined, a row whose *Group*
cell happens to equal the wanted *Name* is declined, and an unset Name declines
nothing at all.

**The bookmark fallback is the operator's addition to #460**, and it is a
preference order rather than a second mechanism: a scanned row carries the
client's own Group cell, so the bot knows what it is going to; a bookmark
carries only what somebody typed. The scanned row therefore always wins, and the
bookmark is what covers a site nobody has scanned down this session --
`Reservoir` being the client's own naming for the wormhole gas sites (Ordinary
and Sizeable Perimeter Reservoir, Vast and Bountiful Frontier Reservoir, Vital
and Instrumental Core Reservoir). A Locations window this bot cannot see is
**not** licence to warp anywhere, and the clause says so in different words from
"there is no such bookmark".

## What is deliberately not here

**Nothing warps.** #460's own scope is the setting, the match and the status
line, and its verification list is entirely about matching; taking the site is
#461's harvest loop. When that lands, the bookmark half should reuse
`eve-online-mining-bot`'s `useContextMenuOnLocationWithMatchingName`, which
already drives a context menu off a `LocationsWindowPlaceEntry` --
`TheHuntIsAChoiceAndNotYetAWarpTest` pins the absence so that the warp arrives
as a decision somebody argues for rather than as drift, and `siteSearch`'s doc
comment names the mechanism so nobody writes a second one.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`, and every
probe-scanner row and every bookmark they are asked about is built by running a
UI tree through the **real** `EveOnline.ParseUserInterface` -- with a real
header row, so what the cases assert on is what `parseProbeScanResult`'s own
"match each cell's x against the header's" produced rather than a `Dict` shaped
by hand. A Python restatement of the match would test the restatement.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode and a rule that answered nothing read identically
from outside, which is the shape `prerequisites.elm_json_literal` exists for.

Confirmed by mutation, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client, a running bot, or the recorded runs.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
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
)

# The probe scanner's own header row, read off a live client on 2026-09-04 and
# quoted in #460: `Signal | Distance | ID | Name | Group`. The geometry is
# explicit because `parseProbeScanResult` maps a cell to a header by asking
# which header's region the cell's midpoint falls inside -- so a fixture with no
# header row produces rows with no cells at all, which is the state this file
# spends most of its time distinguishing from a real answer.
SCAN_COLUMNS = (
    ("Signal", 0, 80),
    ("Distance", 80, 100),
    ("ID", 180, 80),
    ("Name", 260, 200),
    ("Group", 460, 140),
)

# The Group cell a gas site carries, and #456's shipped default.
GAS_SITE = "Gas Site"

# Stock EVE naming for the wormhole gas sites. Not operator-specific, which is
# what lets `bookmarkedGasSiteMarker` ship as a constant rather than a setting.
RESERVOIR_BOOKMARK = "Vast Frontier Reservoir"

# Obviously fictional, per #456: nothing naming a real corporation, structure,
# system or pilot goes in this repository.
OPERATOR_BOOKMARK = "Example Safe Spot"


def label(text, region):
    return node("EveLabelMedium", {"_setText": text}, region=region)


def scan_row(index, cells):
    """One `ScanResultNew` row, with a cell only for the columns named.

    Deliberately **not** nested inside the results scroll:
    `parseProbeScannerWindowFromUITreeRoot` takes the scroll node's own
    contained texts as the column headers, so a row underneath it would have its
    own cells read as headers and every lookup would then miss.
    """
    y = 60 + index * 20
    return node("ScanResultNew", {"_name": "scanResult"}, [
        label(cells[column], (x + 4, y, width - 8, 16))
        for column, x, width in SCAN_COLUMNS if column in cells
    ], region=(0, y, 600, 16))


def probe_scanner(rows, columns=None):
    """The scanner window, open, with a real header row over real rows.

    `columns` is which headers the window draws -- an operator who has not made
    the `Group` column visible has a window whose header row does not name it,
    and then no cell can map to it. That is the state #460 is emphatic about and
    it is produced here by leaving the column out of the client rather than by
    deleting a key from a `Dict`.
    """
    drawn = [c for c in SCAN_COLUMNS
             if columns is None or c[0] in columns]
    scroll = node("Scroll", {"_name": "resultsScroll"}, [
        label(column, (x, 20, width, 16)) for column, x, width in drawn
    ], region=(0, 20, 600, 16))
    return node("ProbeScannerWindow", {"_name": "probeScannerWindow"}, [
        node("Container", {"_name": "ResultsContainer"}, [scroll],
             region=(0, 20, 600, 240)),
    ] + [scan_row(index, cells) for index, cells in enumerate(rows)],
        region=(1000, 100, 600, 300))


def locations_window(bookmark_names):
    """The Locations window, as *this* client renders it.

    `StandaloneBookmarkWnd` rather than `LocationsWindow`: #457 found the parser
    filtering on the second name only, so `locationsWindow` read `Nothing` on
    every reading while the window was open and populated. PR #466 made both
    names match, and this app's vendored parser is re-synced to carry it in the
    same change -- without which the whole fallback below is unreachable and
    would look like a rule that answers nothing.

    One text node per entry, because `parseLocationsWindowPlaceEntry` takes the
    smallest-area text in the row as its `mainText`.
    """
    return node("StandaloneBookmarkWnd", {"_name": "locationsWindow"}, [
        node("PlaceEntry", {"_name": "placeEntry"},
             [label(name, (4, 40 + index * 20, 292, 16))],
             region=(0, 40 + index * 20, 300, 20))
        for index, name in enumerate(bookmark_names)
    ], region=(200, 100, 300, 400))


_TREE_ADDRESS = iter(range(700000, 999999))


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
    """A `let` binding of `name` to a real parsed reading.

    Through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what a case asserts on is what the bot
    would have been handed. `elm_json_literal` rather than a triple-quoted
    literal for the reason its own doc comment gives: Elm processes backslash
    escapes inside `\"\"\"`, so a fixture carrying a double quote decodes to
    `Nothing` and reads exactly like a rule that answered nothing.
    """
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree" % (
                name, elm_json_literal(tree_with(children))))


def search_binding(name, reading):
    """`siteSearch` over a parsed reading's two windows, with the filter given.

    Written out at each call site rather than folded into a helper on the Elm
    side, because what the cases are about is the two windows arriving
    separately -- an absent one has to reach the rule as `Nothing` rather than
    as an empty list.
    """
    return ("%s = %s |> Maybe.map (\\parsed -> siteSearch filter"
            " { probeScannerWindow = parsed.probeScannerWindow"
            ", locationsWindow = parsed.locationsWindow })" % (name, reading))


def elm_string(value):
    return json.dumps(value)


def filter_binding(group=GAS_SITE, name=None):
    return "filter = { group = %s, name = %s }" % (
        elm_string(group),
        "Nothing" if name is None else "Just " + elm_string(name))


class GasHufferRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-group-repl-")
        kwargs.setdefault("app_dir", GAS_HUFFER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    def verdicts(self, expressions, definitions=()):
        """Each verdict rendered whole, constructor and payload.

        `Debug.toString` rather than a battery of equalities per case: it is one
        answer per row that names *which* of the three the rule gave and what it
        carried, so a rule answering the right constructor with the wrong column
        fails rather than passing on whichever equality a case happened to ask.
        """
        return self.strings(["Debug.toString (%s)" % expression
                             for expression in expressions],
                            definitions=list(definitions))


def repl():
    return open_repl(GasHufferRepl)


def row(group=GAS_SITE, name="Ordinary Perimeter Reservoir",
        result_id="ABC-123", signal="100.0%", distance="1.4 AU"):
    """A scan row's cells, as a dict keyed by the column each sits under."""
    cells = {"Signal": signal, "Distance": distance, "ID": result_id,
             "Name": name, "Group": group}
    return cells


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of a row, that the row exists.

    Every case below is of the form "the rule declined this", and a fixture that
    never decoded produces a reading with no scanner window, no rows and no
    cells -- which declines everything, for the wrong reason, silently. So the
    parser's own answer is asserted first: the window is there, the rows are
    there, and the cells are keyed by the header texts the client drew.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_real_parser_keys_the_cells_by_the_real_header_row(self):
        answers = self.repl.strings([
            "Debug.toString (reading |> Maybe.andThen .probeScannerWindow"
            " |> Maybe.map (.scanResults >> List.map .cellsTexts"
            " >> List.map Dict.toList))"
        ], definitions=[reading_binding(
            "reading", [probe_scanner([row()])])])
        printed = answers[0]
        for column, _, _ in SCAN_COLUMNS:
            with self.subTest(column):
                self.assertIn('"%s"' % column, printed)
        self.assertIn('"%s"' % GAS_SITE, printed)

    def test_hiding_the_group_column_removes_the_key_rather_than_emptying_it(self):
        """The state #460 is about, produced the way the client produces it."""
        answers = self.repl.strings([
            "Debug.toString (reading |> Maybe.andThen .probeScannerWindow"
            " |> Maybe.map (.scanResults >> List.map"
            " (.cellsTexts >> Dict.get \"Group\")))"
        ], definitions=[reading_binding("reading", [
            probe_scanner(
                [{k: v for k, v in row().items() if k != "Group"}],
                columns=[c for c, _, _ in SCAN_COLUMNS if c != "Group"])])])
        self.assertEqual(answers[0], "Just [Nothing]")

    def test_the_locations_window_is_read_under_this_clients_type_name(self):
        """Without #466 this answers `Nothing` and the fallback is unreachable."""
        answers = self.repl.strings([
            "Debug.toString (reading |> Maybe.andThen .locationsWindow"
            " |> Maybe.map (.placeEntries >> List.map .mainText))"
        ], definitions=[reading_binding(
            "reading", [locations_window([RESERVOIR_BOOKMARK])])])
        self.assertEqual(answers[0],
                         'Just ["%s"]' % RESERVOIR_BOOKMARK)


class TheGroupColumnIsWhatSaysASiteIsAGasSiteTest(unittest.TestCase):
    """#460's own headline: match on `Group`, not on `Name`.

    Every gas site reads `Group = Gas Site` whatever its Name says, which is the
    whole reason the filter moved columns.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdicts_for(self, rows, group=GAS_SITE, name=None, columns=None):
        return self.repl.verdicts(
            ["Maybe.withDefault [] (Maybe.map (\\r -> r.anomalyVerdicts) search)"],
            definitions=[
                filter_binding(group, name),
                reading_binding("reading",
                                [probe_scanner(rows, columns=columns)]),
                search_binding("search", "reading"),
            ])[0]

    def test_a_row_whose_group_reads_the_hunted_group_is_hunted(self):
        self.assertEqual(self.verdicts_for([row()]), "[HuntThisAnomaly]")

    def test_a_row_whose_group_reads_something_else_is_declined_naming_the_cell(self):
        # The payload matters as much as the constructor: an operator whose
        # wormhole holds only combat sites has to read what the column said.
        self.assertEqual(
            self.verdicts_for([row(group="Combat Site")]),
            '[CellIsNotWhatIsHunted "Group" "Combat Site"]')

    def test_the_name_column_cannot_make_a_non_gas_site_match(self):
        """The move the whole issue is about, asserted from the other side.

        A row named exactly what a gas site is called, in a Group that is not
        one, is declined -- so nothing here has quietly gone back to reading the
        Name.
        """
        self.assertEqual(
            self.verdicts_for([row(group="Combat Site", name=GAS_SITE)]),
            '[CellIsNotWhatIsHunted "Group" "Combat Site"]')

    def test_case_and_surrounding_space_do_not_decide_it(self):
        self.assertEqual(
            self.verdicts_for([row(group="  gas site  ")]),
            "[HuntThisAnomaly]")

    def test_the_match_is_whole_unless_the_entry_ends_in_a_star(self):
        self.assertEqual(
            self.verdicts_for([row(group="Gas Site Deluxe")]),
            '[CellIsNotWhatIsHunted "Group" "Gas Site Deluxe"]')
        self.assertEqual(
            self.verdicts_for([row(group="Gas Site Deluxe")], group="Gas*"),
            "[HuntThisAnomaly]")

    def test_a_star_elsewhere_is_a_literal(self):
        self.assertEqual(
            self.verdicts_for([row()], group="Gas*Site"),
            '[CellIsNotWhatIsHunted "Group" "%s"]' % GAS_SITE)

    def test_several_rows_are_judged_one_by_one(self):
        # And the hunted one is picked out of the middle rather than the head,
        # so a rule that answered about `List.head` alone fails.
        self.assertEqual(
            self.verdicts_for([row(group="Combat Site"), row(),
                               row(group="Relic Site")]),
            '[CellIsNotWhatIsHunted "Group" "Combat Site",HuntThisAnomaly,'
            'CellIsNotWhatIsHunted "Group" "Relic Site"]')


class AMissingGroupColumnIsNotAMatchTest(unittest.TestCase):
    """The failure this whole design refuses.

    `Dict.get` answering `Nothing` means "cannot tell", and the permissive
    reading of that warps the ship into an unidentified site in a wormhole. The
    mutation #460 names by hand -- defaulting an absent Group to a match -- is
    what `test_a_row_with_no_group_cell_is_declined` fails.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    NO_GROUP_COLUMNS = [c for c, _, _ in SCAN_COLUMNS if c != "Group"]

    def ungrouped_row(self):
        return {k: v for k, v in row().items() if k != "Group"}

    def search_over_ungrouped(self, extra_rows=(), bookmarks=None):
        children = [probe_scanner(
            [self.ungrouped_row()] + list(extra_rows),
            columns=self.NO_GROUP_COLUMNS)]
        if bookmarks is not None:
            children.append(locations_window(bookmarks))
        return [filter_binding(),
                reading_binding("reading", children),
                search_binding("search", "reading")]

    def test_a_row_with_no_group_cell_is_declined(self):
        self.assertEqual(
            self.repl.verdicts(
                ["Maybe.withDefault [] (Maybe.map .anomalyVerdicts search)"],
                definitions=self.search_over_ungrouped())[0],
            '[ColumnIsNotInTheReading "Group"]')

    def test_and_nothing_is_hunted_on_that_reading(self):
        # The verdict declining is not on its own the property: what matters is
        # that the search does not go on to take the row anyway.
        self.assertEqual(
            self.repl.verdicts(
                ["Maybe.andThen .hunted search |> Maybe.map (always ())"],
                definitions=self.search_over_ungrouped(bookmarks=[]))[0],
            "Nothing")

    def test_the_status_line_says_the_column_is_absent_and_counts_the_rows(self):
        """#460's second half: an operator has to see *why* nothing is hunted.

        Silence here reads exactly like a wormhole with no gas site in it, and
        the two are fixed in entirely different places.
        """
        clause = self.repl.strings(
            ["Maybe.withDefault \"<no reading>\""
             " (Maybe.map describeSiteSearch search)"],
            definitions=self.search_over_ungrouped(
                extra_rows=[self.ungrouped_row()], bookmarks=[]))[0]
        self.assertIn("NO 'Group' COLUMN", clause)
        self.assertIn("2 of 2 result(s)", clause)
        self.assertIn("declines them", clause)
        self.assertIn("Make that column visible", clause)
        self.assertIn("NOTHING TO HUNT", clause)

    def test_that_clause_is_absent_where_every_column_is_there(self):
        # Without this the case above is satisfied by a clause printed on every
        # reading, which is a clause an operator stops seeing.
        clause = self.repl.strings(
            ["Maybe.withDefault \"<no reading>\""
             " (Maybe.map describeSiteSearch search)"],
            definitions=[
                filter_binding(),
                reading_binding("reading", [probe_scanner(
                    [row(group="Combat Site")]), locations_window([])]),
                search_binding("search", "reading"),
            ])[0]
        self.assertNotIn("NO 'Group' COLUMN", clause)
        self.assertIn("0 of 1 result(s)", clause)
        self.assertIn("NOTHING TO HUNT", clause)

    def test_a_hidden_column_is_still_reported_where_another_row_matched(self):
        """A column absent from half the scanner is worth saying either way.

        `anomalyVerdicts` keeps an answer for every row rather than only the
        declined ones, which is what makes this expressible -- and a reading
        where the bot found something to do is exactly where a half-configured
        scanner would otherwise go unmentioned for the rest of the session.
        """
        clause = self.repl.strings(
            ["Maybe.withDefault \"<no reading>\""
             " (Maybe.map describeSiteSearch search)"],
            definitions=[
                filter_binding(),
                # A window drawing the Group header, one row carrying that cell
                # and one row that does not.
                reading_binding("reading", [probe_scanner(
                    [row(), {k: v for k, v in row().items() if k != "Group"}])]),
                search_binding("search", "reading"),
            ])[0]
        self.assertIn("would hunt the scanned anomaly", clause)
        self.assertIn("NO 'Group' COLUMN on 1 of 2 result(s)", clause)


class TheNameFilterIsIndependentOfTheGroupTest(unittest.TestCase):
    """#460's other emphasis: if both are set, both must hold.

    Two entries in one list, neither reading the other's cell. The cross is what
    a folded implementation gets wrong, so the cross is what is asked.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdict_for(self, cells, group=GAS_SITE, name=None, columns=None):
        return self.repl.verdicts(
            ["Maybe.withDefault [] (Maybe.map .anomalyVerdicts search)"],
            definitions=[
                filter_binding(group, name),
                reading_binding(
                    "reading", [probe_scanner([cells], columns=columns)]),
                search_binding("search", "reading"),
            ])[0]

    def test_an_unset_name_declines_nothing(self):
        self.assertEqual(
            self.verdict_for(row(name="Anything At All")),
            "[HuntThisAnomaly]")

    def test_group_and_name_both_matching_is_hunted(self):
        self.assertEqual(
            self.verdict_for(row(name="Vast Frontier Reservoir"),
                             name="Vast Frontier Reservoir"),
            "[HuntThisAnomaly]")

    def test_a_row_matching_group_but_not_a_set_name_is_declined(self):
        # #460's third verification item, by name.
        self.assertEqual(
            self.verdict_for(row(name="Sizeable Perimeter Reservoir"),
                             name="Vast Frontier Reservoir"),
            '[CellIsNotWhatIsHunted "Name" "Sizeable Perimeter Reservoir"]')

    def test_a_row_matching_a_set_name_but_not_the_group_is_declined(self):
        # The other direction, so neither condition can excuse the other.
        self.assertEqual(
            self.verdict_for(row(group="Combat Site", name="Vast Frontier"),
                             name="Vast Frontier"),
            '[CellIsNotWhatIsHunted "Group" "Combat Site"]')

    def test_the_name_is_never_matched_against_the_group_cell(self):
        """The fold this refuses, made unambiguous.

        A row whose *Group* cell is exactly what `anomaly-name` asks for, and
        whose Name is not, must be declined -- a rule that looked the name up in
        the wrong column would hunt it.
        """
        self.assertEqual(
            self.verdict_for(row(name="Something Else"), name=GAS_SITE),
            '[CellIsNotWhatIsHunted "Name" "Something Else"]')

    def test_a_missing_name_column_declines_only_where_the_name_is_set(self):
        no_name = [c for c, _, _ in SCAN_COLUMNS if c != "Name"]
        cells = {k: v for k, v in row().items() if k != "Name"}
        self.assertEqual(
            self.verdict_for(cells, columns=no_name),
            "[HuntThisAnomaly]")
        self.assertEqual(
            self.verdict_for(cells, name="Vast Frontier", columns=no_name),
            '[ColumnIsNotInTheReading "Name"]')

    def test_the_group_reason_is_the_one_reported_where_both_fail(self):
        # One reason per row, and the first is the one to fix first: a Group
        # column that is not there is what stops the Name mattering.
        self.assertEqual(
            self.verdict_for(row(group="Combat Site", name="Nope"),
                             name="Vast Frontier"),
            '[CellIsNotWhatIsHunted "Group" "Combat Site"]')

    def test_the_filter_is_two_entries_in_one_list(self):
        """Structural, because the executable cases cannot see a rewrite that
        happens to agree with them on these inputs.

        What a folded implementation looks like is a `case` on the name nested
        inside the group's branch, and it would pass every case above while
        being one edit from letting a name match excuse the group.
        """
        body = collapsed(block("anomalyVerdict"))
        self.assertIn("columnMustRead anomalyGroupColumn filter.group", body)
        self.assertIn(
            "filter.name |> Maybe.andThen (columnMustRead anomalyNameColumn)",
            body)
        self.assertIn("List.filterMap identity", body)


class TheBookmarkFallbackTest(unittest.TestCase):
    """A `Reservoir` bookmark, where nothing has been scanned down.

    The operator's addition to #460. It is a preference order rather than an
    alternative: a scanned row carries the client's own Group cell, a bookmark
    carries only what somebody typed, so the scanned row wins wherever there is
    one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def hunted(self, rows, bookmarks=None, name=None):
        """What the bot says it would take, through the shipped clause.

        `describeSiteHunted` rather than a `case` written here: the repl takes
        one entry per question and a multi-line `case` does not survive that
        shape, and the clause is the thing an operator reads anyway -- so this
        discriminates the two sources *and* the wording in one answer.
        """
        children = [probe_scanner(rows)]
        if bookmarks is not None:
            children.append(locations_window(bookmarks))
        return self.repl.strings(
            ["Maybe.withDefault \"<no reading>\""
             " (Maybe.map describeSiteHunted search)"],
            definitions=[
                filter_binding(name=name),
                reading_binding("reading", children),
                search_binding("search", "reading"),
            ])[0]

    def test_with_nothing_scanned_a_reservoir_bookmark_is_taken(self):
        clause = self.hunted([row(group="Combat Site")],
                             bookmarks=[OPERATOR_BOOKMARK, RESERVOIR_BOOKMARK])
        self.assertIn("falling back to the bookmark '%s'" % RESERVOIR_BOOKMARK,
                      clause)
        self.assertIn("nothing scanned reads Group '%s'" % GAS_SITE, clause)
        # The first matching bookmark, not the first bookmark.
        self.assertNotIn(OPERATOR_BOOKMARK, clause)

    def test_a_scanned_gas_site_outranks_the_bookmark(self):
        clause = self.hunted([row(result_id="AIC-176")],
                             bookmarks=[RESERVOIR_BOOKMARK])
        self.assertIn("would hunt the scanned anomaly 'AIC-176'", clause)
        self.assertIn("(Ordinary Perimeter Reservoir)", clause)
        self.assertNotIn("bookmark", clause)

    def test_a_bookmark_that_is_not_a_reservoir_is_not_a_site(self):
        self.assertIn("NOTHING TO HUNT",
                      self.hunted([row(group="Combat Site")],
                                  bookmarks=[OPERATOR_BOOKMARK]))

    def test_the_marker_is_matched_as_a_substring_ignoring_case(self):
        # A bookmark's name is whatever the operator typed around the client's
        # own word, where a Group cell is a field the client fills in.
        self.assertIn(
            "falling back to the bookmark 'gas 3 - vital core reservoir (deep)'",
            self.hunted([row(group="Combat Site")],
                        bookmarks=["gas 3 - vital core reservoir (deep)"]))

    def test_a_locations_window_this_bot_cannot_see_is_not_licence_to_go_anywhere(self):
        self.assertIn("NOTHING TO HUNT",
                      self.hunted([row(group="Combat Site")], bookmarks=None))

    def test_the_clause_tells_a_shut_window_from_an_empty_one(self):
        """The two states want different fixes from the operator.

        One is a window they never opened; the other is a bookmark they never
        made. A clause that said "no bookmark" for both would send them to the
        wrong one.
        """
        shut, empty, present = self.repl.strings(
            ["Maybe.withDefault \"<no reading>\""
             " (Maybe.map describeBookmarksForHunting %s)" % name
             for name in ("shut", "empty", "present")],
            definitions=[
                filter_binding(),
                reading_binding("shutReading", [probe_scanner([])]),
                reading_binding("emptyReading",
                                [probe_scanner([]), locations_window([])]),
                reading_binding("presentReading", [
                    probe_scanner([]),
                    locations_window([RESERVOIR_BOOKMARK, OPERATOR_BOOKMARK])]),
                search_binding("shut", "shutReading"),
                search_binding("empty", "emptyReading"),
                search_binding("present", "presentReading"),
            ])
        self.assertIn("Locations window is not open", shut)
        self.assertIn("different thing", shut)
        self.assertNotIn("Locations window is not open", empty)
        self.assertIn("no bookmark's name carries", empty)
        self.assertIn("1 bookmark(s)", present)

    def test_the_marker_is_the_clients_own_site_naming(self):
        """A constant rather than a setting, and why.

        #456's rule is that anything identifying an *operator* -- a corporation,
        a structure, a system, a naming convention of their own -- is a setting
        with no default in code. `Reservoir` identifies the game's own site
        family, exactly as `Gas Site` does, so shipping it names nobody.
        """
        self.assertEqual(self.repl.strings(["bookmarkedGasSiteMarker"]),
                         ["Reservoir"])
        doc = bot_source().split("bookmarkedGasSiteMarker :", 1)[0] \
            .rsplit("{-|", 1)[1]
        self.assertIn("#456", doc)
        for stock_name in ("Perimeter Reservoir", "Frontier Reservoir",
                           "Core Reservoir"):
            with self.subTest(stock_name):
                self.assertIn(stock_name, doc)


class TheProbeScannerClauseSaysWhatItSawTest(unittest.TestCase):
    """The three states a scanner can be in, told apart.

    Not open at all, open with nothing on it, and open with rows none of which
    match are three different things and only the first is a client-setup
    problem.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def clause(self, children):
        return self.repl.strings(
            ["Maybe.withDefault \"<no reading>\""
             " (Maybe.map describeProbeScannerForHunting search)"],
            definitions=[
                filter_binding(),
                reading_binding("reading", children),
                search_binding("search", "reading"),
            ])[0]

    def test_a_shut_scanner_says_so_rather_than_reporting_no_results(self):
        clause = self.clause([locations_window([])])
        self.assertIn("probe scanner window is not open", clause)
        self.assertIn("client-setup list", clause)

    def test_an_open_empty_scanner_says_that_instead(self):
        clause = self.clause([probe_scanner([])])
        self.assertIn("open and shows no results", clause)
        self.assertNotIn("not open", clause)

    def test_an_open_scanner_counts_what_matched(self):
        clause = self.clause([probe_scanner(
            [row(), row(group="Combat Site"), row()])])
        self.assertIn("2 of 3 result(s)", clause)
        self.assertIn("Group '%s'" % GAS_SITE, clause)

    def test_the_clause_names_the_name_filter_where_one_is_set(self):
        both, group_only = self.repl.strings([
            "describeAnomalyFilter { group = %s, name = Just %s }"
            % (elm_string(GAS_SITE), elm_string("Vast Frontier")),
            "describeAnomalyFilter { group = %s, name = Nothing }"
            % elm_string(GAS_SITE),
        ])
        self.assertIn("Group '%s'" % GAS_SITE, both)
        self.assertIn("Name 'Vast Frontier'", both)
        self.assertIn("any Name", group_only)
        self.assertNotIn("and Name", group_only)


class TheColumnNamesAreWrittenDownOnceTest(unittest.TestCase):
    """#102's shape applied to a string rather than to a counter.

    The rule and the sentence telling an operator to make a column visible have
    to mean the same column. A clause naming `Group` while the lookup read
    something else would present as a client that is set up wrong, which is the
    one diagnosis that sends nobody near the bug.
    """

    def test_the_lookup_and_the_clause_read_the_same_declaration(self):
        source = bot_source()
        declarations = top_level_declarations(source)
        self.assertEqual(collapsed(declarations["anomalyGroupColumn"]).strip(),
                         'anomalyGroupColumn : String anomalyGroupColumn = "Group"')
        # The literal appears in the declaration and nowhere else in any body,
        # so neither the rule nor the clause can carry its own copy.
        bodies = {name: collapsed(text) for name, text in declarations.items()
                  if name not in ("anomalyGroupColumn", "anomalyNameColumn")}
        with_literal = [name for name, text in bodies.items()
                        if '"Group"' in text or '"Name"' in text]
        self.assertEqual(with_literal, [], with_literal)

    def test_both_readers_name_the_declaration(self):
        self.assertIn("anomalyGroupColumn", collapsed(block("anomalyVerdict")))
        self.assertIn("anomalyGroupColumn",
                      collapsed(block("describeColumnsTheScannerDoesNotShow")))


class TheSearchIsOneDeclarationWithSeveralReadersTest(unittest.TestCase):
    """The decision and the status line ask the same question once.

    #102 is one fact settled in one place and read in another, and the way it
    would fail here is a status line reporting a site the decision was not
    acting on. Two callers of one pure function over one reading cannot
    disagree, so what is pinned is that there is exactly one such function and
    that both go through it.
    """

    def test_the_decision_branch_and_the_status_line_both_go_through_it(self):
        self.assertIn("siteSearchFromContext", collapsed(block("huntForASite")))
        self.assertIn("siteSearchFromContext",
                      collapsed(block("statusTextFromState")))

    def test_nothing_else_builds_a_search_of_its_own(self):
        callers = [name for name, text in top_level_declarations(
            bot_source()).items()
            if "siteSearch " in collapsed(text) and name != "siteSearch"]
        self.assertEqual(callers, ["siteSearchFromContext"], callers)

    def test_the_in_space_branch_is_the_hunt(self):
        root = collapsed(block("gasHufferDecisionRootBeforeApplyingSettings"))
        self.assertIn("ifSeeShipUI = \\_ -> huntForASite context", root)

    def test_the_rule_takes_a_reading_rather_than_a_decision_context(self):
        """#106's lesson: a rule reachable only through a `BotDecisionContext`
        is a rule nothing can execute, so it gets checked by being read."""
        signature = collapsed(block("siteSearch")).split(" siteSearch filter")[0]
        self.assertIn("siteSearch : AnomalyFilter -> SiteSearchReading"
                      " -> SiteSearch", signature)
        self.assertNotIn("BotDecisionContext", signature)


class TheHuntIsAChoiceAndNotYetAWarpTest(unittest.TestCase):
    """Nothing here flies anywhere, pinned while that is still true.

    #460 asked for the filter and the status line; taking the site is #461. The
    case is here so that the warp arrives as a decision somebody argues for
    rather than as drift -- and so that whoever writes it reads `siteSearch`'s
    doc comment, which names the mechanism to reuse rather than leaving a second
    one to be reconciled later.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_hunt_branch_dispatches_no_effects(self):
        body = collapsed(block("huntForASite"))
        self.assertIn("waitForProgressInGame", body)
        for acting in ("useContextMenuCascade", "decideActionForCurrentStep",
                       "mouseClickOnUIElement", "EffectOnWindow"):
            with self.subTest(acting):
                self.assertNotIn(acting, body)

    def test_the_in_space_leaf_still_says_it_is_doing_nothing_on_purpose(self):
        text = self.repl.strings(["nothingToDoInSpaceYet"])[0]
        self.assertIn("on purpose", text)
        self.assertIn("#460", text)
        self.assertIn("#461", text)

    def test_the_doc_comment_names_the_mechanism_the_warp_should_reuse(self):
        doc = bot_source().split("siteSearch : AnomalyFilter", 1)[0] \
            .rsplit("{-|", 1)[1]
        self.assertIn("useContextMenuOnLocationWithMatchingName", doc)
        self.assertIn("eve-online-mining-bot", doc)
        self.assertIn("#461", doc)

    def test_that_mechanism_is_still_where_the_doc_comment_says_it_is(self):
        """A pointer at a function that has been renamed is worse than none."""
        mining_bot = os.path.join(
            os.path.dirname(GAS_HUFFER_DIR), "eve-online-mining-bot",
            "Bot.elm")
        with open(mining_bot, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("useContextMenuOnLocationWithMatchingName :", source)
        self.assertIn("locationsWindow", source)


class TheMutationsThisFileCatches(unittest.TestCase):
    """The list, so that a later reader can re-run them rather than trust it.

    Each of these fails at least one named case above. They are recorded rather
    than executed -- this suite has no mutation runner -- and the count is what
    the PR body quotes.

    1. an absent `Group` column defaulting to a match, which is the mutation
       #460 names by hand and the failure this whole design refuses.
    2. an absent `Name` column defaulting to a match where a name is set.
    3. the name condition nested inside the group's branch, so a folded
       implementation passes the executable cases.
    4. the name looked up in the `Group` column.
    5. the group looked up in the `Name` column.
    6. `anomalyVerdict` answering `HuntThisAnomaly` when *either* condition
       holds rather than both.
    7. an unset `anomaly-name` contributing an entry that compares against the
       empty string.
    8. `siteCellMatches` weakened to `String.contains`.
    9. `siteCellMatches` made case-sensitive.
    10. the trailing-`*` prefix dropped.
    11. `anomalyGroupColumn` spelled as a literal at the lookup while the clause
        keeps the declaration.
    12. the missing-column clause dropped from the status line.
    13. that clause printed on every reading rather than only where a column is
        absent.
    14. `anomalyVerdicts` narrowed to the declined rows, so a hidden column goes
        unreported on a reading that found something.
    15. the bookmark preferred over a scanned anomaly.
    16. the bookmark marker matched exactly rather than as a substring.
    17. an absent Locations window read as an empty one, so the clause stops
        telling a shut window from one with no such bookmark.
    18. the status line building its own `siteSearch` rather than going through
        `siteSearchFromContext`.
    19. the in-space branch reverted to `nothingToDoInSpaceYet` alone.
    20. the vendored parser reverted to its pre-#466 copy, so `locationsWindow`
        answers `Nothing` for this client and the whole fallback is unreachable.
    """

    def test_the_list_is_a_list(self):
        """`\\s*` rather than `\\s+`: Python 3.13 dedents a docstring at compile
        time, so the numbered lines reach here at column zero on a new
        interpreter and indented on an old one."""
        mutations = re.findall(r"^\s*\d+\. ", self.__doc__, re.M)
        self.assertEqual(
            len(mutations), 20,
            "the mutation list is not the length the PR body quotes")


if __name__ == "__main__":
    unittest.main()
