"""Issue #458 -- the Directional Scanner's rows are read, cell by cell.

`DirectionalScannerWindow.scanResults` has been parsed on every reading in
every vendored copy of `EveOnline/ParseUserInterface.elm` since the type was
added, and **nothing anywhere in the repository ever extracted a cell of text
from it**. The only reader is `eve-online-wingman`, which asks whether the
window's own `uiNode` is present for stray-window handling and reads no
content. So the bot could not see what was on D-Scan.

`parseDirectionalScanResult` is what changes that, and the whole of its
difficulty is that `parseProbeScanResult`'s technique does not transfer. That
one builds its `cellsTexts` by matching each cell's horizontal position against
the labels of that window's own header row; **the Directional Scanner draws no
header row at all**, so there is nothing to match against and the columns have
to be read by position instead.

What these cases execute, rather than restate:

- rows built to the shape measured on a live client parse to their three cells,
  through the **real** `EveOnline.ParseUserInterface` reached through the real
  `decodeMemoryReadingFromString`, so what is asserted is what a bot would have
  been handed;
- a cell that cannot be read answers `Nothing` and never `""`, which is the
  load-bearing half: the consumer this exists for reads an unreadable name as
  hostile, and a defaulted empty string would make an unknown ship look safe;
- a row of any other shape reads as three `Nothing`s rather than throwing and
  rather than mis-assigning its cells, which is the same distinction one step
  further out;
- the new block is byte-identical across every vendored copy.

**Unverified, and it is the case the downstream feature exists for.** Every row
measured on the live client was a *structure*. Whether a row for a piloted ship
has the same four-container shape is not known, so these fixtures are built
from the structure shape that was measured and the parser declines to read
anything else. Every name in them is fictional.
"""

import glob
import os
import re
import unittest

from prerequisites import (ElmRepl, MISSION_RUNNER_DIR, REPO_DIR,
                           elm_json_literal, open_repl, vendored_parser_count)

APPS_DIR = os.path.join(REPO_DIR, "implement", "applications", "eve-online")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# The row shape read off a live client on 2026-09-04: four direct `Container`
# children of a `DirectionalScanResultEntry`, at these local x-offsets. The
# first carries the icon and no text; the other three are the columns.
#
# `_displayX` in a UI tree is local to the parent and `totalDisplayRegion`
# accumulates the inherited offset, so these are the measured numbers put in
# the fixture unchanged rather than converted into anything.
CELL_OFFSETS = (0, 19, 179, 309)
CELL_WIDTHS = (19, 160, 130, 100)

# Deliberately fictional. The client's own strings for these columns are the
# operator's business and none of them is needed to test a positional read.
STRUCTURE_ROWS = (
    ("Fictional IX - Example Waystation", "Example Citadel", "8.3 AU"),
    ("Fictional IX - Second Example Post", "Example Refinery", "12.6 AU"),
    ("Fictional VII - Third Example Post", "Example Citadel", "0.4 AU"),
)

# What `describeCell` prints, so that `Nothing` and `Just ""` cannot both come
# back as the empty string -- which is the one distinction every case below
# turns on.
NOTHING = "<nothing>"
NO_ROW = "<no row>"


def just(text):
    return "<just>" + text


_address = iter(range(100000, 999999))


def node(type_name, entries=None, children=(), region=None):
    """One UI tree node in the shape `decodeMemoryReadingFromString` wants."""
    dict_entries = dict(entries or {})
    if region is not None:
        x, y, width, height = region
        dict_entries.update({
            "_displayX": x, "_displayY": y,
            "_displayWidth": width, "_displayHeight": height,
        })
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": dict_entries,
        "children": list(children),
    }


def label(text, width):
    """A label carrying `text`, the way the client draws a cell's contents.

    Given a display region, which is what makes a row's *children* different
    from its *descendants*: a cell's label is one of the latter and not one of
    the former, so a rule that walked the whole subtree instead of the direct
    children would count seven nodes where the layout has four. The text
    itself is reached through `getAllContainedDisplayTexts`, which walks the
    raw tree and does not care either way.
    """
    return node("EveLabelMedium", {"_name": "label", "_setText": text},
                region=(0, 0, width, 16))


def cell(index, texts=()):
    """One of a row's direct `Container` children, at its measured offset."""
    return node(
        "Container",
        {"_name": "cell"},
        [label(text, CELL_WIDTHS[index]) for text in texts],
        region=(CELL_OFFSETS[index], 0, CELL_WIDTHS[index], 20))


def structure_row(name, type_text, distance, top=0):
    """A `DirectionalScanResultEntry` in the shape measured on a live client."""
    return row_of_cells(
        [cell(0), cell(1, [name]), cell(2, [type_text]), cell(3, [distance])],
        top=top)


def row_of_cells(cells, top=0):
    return node("DirectionalScanResultEntry", {}, cells,
                region=(0, top, 440, 20))


def scanner_window(rows):
    """The `DirectionalScanner` window, with the scroll node the parser wants.

    `parseDirectionalScannerWindowFromUITreeRoot` takes the largest descendant
    whose type name contains "scroll", and looks for the rows under that -- so a
    fixture that skipped it would parse to a window with no rows at all and
    every case below would be asserting against an empty list.
    """
    return node("DirectionalScanner", {"_name": "dscan"}, [
        node("ScrollControls", {"_name": "scroll"}, rows,
             region=(0, 30, 440, 400)),
    ], region=(600, 100, 460, 480))


def tree_with(children):
    return node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


def reading_binding(name, children):
    """A `let`-free binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what the cases assert on is what the bot
    would have been handed rather than a record shaped by hand.

    The literal comes from `elm_json_literal` rather than being written out
    here, because getting that wrong is not a broken fixture -- it is a case
    that passes having asserted against a reading that never arrived.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, elm_json_literal(tree_with(children)))


# The helpers every case asks its questions through. `describeCell` is what
# keeps `Nothing` and `Just ""` apart in an answer the repl prints as a
# `String`, and `cellOf` distinguishes a row that is not there from a cell that
# could not be read -- without which a fixture that parsed to no rows at all
# would answer exactly like a parser refusing to read cells.
HELPERS = (
    'describeCell maybeText ='
    ' Maybe.withDefault "%s" (Maybe.map (\\text -> "<just>" ++ text) maybeText)'
    % NOTHING,
    'rowsOf reading = reading |> Maybe.andThen .directionalScannerWindow'
    ' |> Maybe.map .scanResults |> Maybe.withDefault []',
    'cellOf index field rows = rows |> List.drop index |> List.head'
    ' |> Maybe.map (field >> describeCell) |> Maybe.withDefault "%s"' % NO_ROW,
)


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def parser_paths():
    return sorted(glob.glob(
        os.path.join(APPS_DIR, "*", "EveOnline", "ParseUserInterface.elm")))


def app_of(path):
    return os.path.basename(os.path.dirname(os.path.dirname(path)))


def result_alias(source):
    """The `DirectionalScanResult` type alias, sliced rather than searched for.

    `elm-format` puts exactly two blank lines between top-level declarations, so
    the end of the slice is structural rather than a guess.
    """
    start = source.index("type alias DirectionalScanResult =")
    return source[start:source.index("\n\n\n", start)]


def result_function(source):
    """`parseDirectionalScanResult`, doc comment and all.

    Sliced rather than searched for by substring: a case asserting that some
    string occurs somewhere in a 21,000-line file passes for a copy carrying
    the declaration under a different name, or twice, or unreachable. The doc
    comment is inside the slice on purpose -- it is where the shape this rests
    on and what is still unverified about it are written down, and a copy that
    dropped it would be a copy a reader cannot get that from.
    """
    start = source.index("{-| Reads a Directional Scanner row")
    body = source[start:source.index("\n\n\n", start)]
    if "parseDirectionalScanResult scanResultNode =" not in body:
        raise AssertionError(
            "the slice does not reach the function it is supposed to cover")
    return body


class Repl(ElmRepl):
    """The shared harness with the parser modules the fixtures need."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "dscan-cells-repl-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class TheRowShapeMeasuredOnALiveClientTest(unittest.TestCase):
    """The measured shape, parsed. Everything else is a departure from this."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(Repl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions(self):
        return list(HELPERS) + [
            reading_binding("scan", [scanner_window([
                structure_row(name, type_text, distance, top=30 * index)
                for index, (name, type_text, distance)
                in enumerate(STRUCTURE_ROWS)])]),
            reading_binding("noScanner", []),
        ]

    def test_the_fixture_parses_into_the_window_the_cases_assume(self):
        """The tree first, before anything is concluded from it.

        A fixture the parser makes nothing of would answer `<no row>` for every
        cell, which is indistinguishable from a parser that reads no cells --
        so the row count is asserted before any cell is.
        """
        answers = self.repl.evaluate(
            ["(scan |> Maybe.map (.directionalScannerWindow >> (/=) Nothing))"
             " == Just True",
             "(List.length (rowsOf scan)) == %d" % len(STRUCTURE_ROWS),
             "(noScanner |> Maybe.map"
             " (.directionalScannerWindow >> (==) Nothing)) == Just True"],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True, True, True],
            "the parser does not make of this tree what the cases below "
            "assume it does, so nothing they conclude would mean anything")

    def test_every_row_answers_its_three_cells(self):
        """Name, Type and Distance, off the measured layout, for every row.

        Every row rather than the first, because an off-by-one in the cell
        indices is invisible in a fixture whose columns happen to look alike --
        and because a rule answering the first row correctly and the rest not
        at all is a rule that reads something other than the row it was given.
        """
        expressions = []
        expected = []
        for index, (name, type_text, distance) in enumerate(STRUCTURE_ROWS):
            for field, value in (("name", name), ("type_", type_text),
                                 ("distance", distance)):
                expressions.append(
                    "cellOf %d .%s (rowsOf scan)" % (index, field))
                expected.append(just(value))
        self.assertEqual(
            self.repl.strings(expressions, definitions=self.definitions()),
            expected)

    def test_the_columns_are_not_read_in_one_anothers_places(self):
        """The Name is the Name and the Type is the Type.

        Stated separately from the case above because it is the mutation this
        file most has to catch: swapping two of the three cell indices leaves
        every row still answering three strings, and a case comparing a set or
        a sorted list would pass on it. So the two columns are asserted to hold
        each other's value in *neither* direction, on a row where they differ.
        """
        name, type_text, _ = STRUCTURE_ROWS[0]
        self.assertNotEqual(
            name, type_text, "the fixture cannot show a swap if they agree")
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf scan)", "cellOf 0 .type_ (rowsOf scan)"],
            definitions=self.definitions())
        self.assertEqual(answers, [just(name), just(type_text)])
        self.assertNotEqual(
            answers, [just(type_text), just(name)],
            "the Name and Type columns are being read in each other's places")

    def test_the_cells_are_taken_left_to_right_rather_than_in_tree_order(self):
        """A row whose children are in the tree in some other order.

        The columns are a horizontal layout, so which cell is the Name is a
        question about position and not about the order a tree walk happens to
        yield. The fixture puts the four containers in the tree back to front,
        with their measured offsets unchanged, and the answer has to be the
        same.
        """
        name, type_text, distance = STRUCTURE_ROWS[0]
        cells = [cell(0), cell(1, [name]), cell(2, [type_text]),
                 cell(3, [distance])]
        scrambled = row_of_cells(list(reversed(cells)))
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf reversedRow)",
             "cellOf 0 .type_ (rowsOf reversedRow)",
             "cellOf 0 .distance (rowsOf reversedRow)"],
            definitions=list(HELPERS) + [
                reading_binding("reversedRow", [scanner_window([scrambled])])])
        self.assertEqual(
            answers, [just(name), just(type_text), just(distance)],
            "the cells are being read in tree order rather than left to right")


class AnUnreadableCellAnswersNothingRatherThanEmptyTest(unittest.TestCase):
    """`Nothing` and `""` are different answers, and this is the whole point.

    The consumer #458 was filed for reads a row it cannot name as *hostile*.
    That only works while "this parser could not read a name" and "the name is
    the empty string" are distinguishable, so a cell defaulted to `""` would
    silently turn an unreadable ship into one that matches nothing and reads as
    safe. Every case here asks for the distinction directly.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(Repl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions(self):
        name, type_text, distance = STRUCTURE_ROWS[0]
        return list(HELPERS) + [
            # The Name cell is there and holds no label at all.
            reading_binding("noLabel", [scanner_window([row_of_cells([
                cell(0), cell(1), cell(2, [type_text]),
                cell(3, [distance])])])]),
            # The Name cell holds a label whose text is empty.
            reading_binding("emptyText", [scanner_window([row_of_cells([
                cell(0), cell(1, [""]), cell(2, [type_text]),
                cell(3, [distance])])])]),
            # And one whose text is nothing but spaces, which is the same
            # answer with a different way of arriving at it.
            reading_binding("blankText", [scanner_window([row_of_cells([
                cell(0), cell(1, ["   "]), cell(2, [type_text]),
                cell(3, [distance])])])]),
            # A cell carrying an empty label before a real one: the blank is
            # skipped rather than being taken as the cell's answer.
            reading_binding("blankThenReal", [scanner_window([row_of_cells([
                cell(0), cell(1, ["", name]), cell(2, [type_text]),
                cell(3, [distance])])])]),
        ]

    def test_a_cell_with_nothing_in_it_answers_nothing(self):
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf noLabel)",
             "cellOf 0 .name (rowsOf emptyText)",
             "cellOf 0 .name (rowsOf blankText)"],
            definitions=self.definitions())
        self.assertEqual(
            answers, [NOTHING, NOTHING, NOTHING],
            "an unreadable cell is answering with a string, which is what "
            "makes an unknown ship match a list of friendly names")

    def test_one_unreadable_cell_does_not_collapse_the_others(self):
        """The other two columns are still answered, and still their own.

        A rule that gave up on the whole row for one missing cell would be
        fail-safe and useless: the Type and Distance are exactly what is left
        to go on when a name cannot be read.
        """
        _, type_text, distance = STRUCTURE_ROWS[0]
        for reading in ("noLabel", "emptyText", "blankText"):
            with self.subTest(reading=reading):
                answers = self.repl.strings(
                    ["cellOf 0 .type_ (rowsOf %s)" % reading,
                     "cellOf 0 .distance (rowsOf %s)" % reading],
                    definitions=self.definitions())
                self.assertEqual(answers, [just(type_text), just(distance)])

    def test_a_blank_label_beside_a_real_one_does_not_win(self):
        name, _, _ = STRUCTURE_ROWS[0]
        [answer] = self.repl.strings(
            ["cellOf 0 .name (rowsOf blankThenReal)"],
            definitions=self.definitions())
        self.assertEqual(
            answer, just(name),
            "an empty label is being taken as the cell's text in preference "
            "to the real one beside it")


class ARowOfAnotherShapeIsDeclinedRatherThanMisreadTest(unittest.TestCase):
    """The case the live measurement could not settle, failing safe.

    Every row measured was a structure. If a piloted ship's row carries a
    container nobody predicted -- a corporation ticker, say -- then a rule that
    took indices out of a list of a different length would read that container
    as the Name, and a consumer matching it against a list of friendly names
    could find an unknown ship safe. A row this parser declines to read is one
    such a consumer treats as hostile; a row it mis-assigns is not.

    So the answer to any other shape is three `Nothing`s, and these cases pin
    that in both directions: nothing is thrown, and no cell is filled from a
    position that was not measured to hold it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(Repl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions(self):
        name, type_text, distance = STRUCTURE_ROWS[0]
        extra = "EXMPL"
        return list(HELPERS) + [
            # One container more than the measured shape, carrying a string
            # ahead of the name -- the corporation-ticker hypothesis, built so
            # that a rule reading positions blind would answer `extra` for the
            # Name and `name` for the Type.
            reading_binding("fiveCells", [scanner_window([
                node("DirectionalScanResultEntry", {}, [
                    cell(0),
                    node("Container", {"_name": "extra"}, [label(extra, 60)],
                         region=(19, 0, 60, 20)),
                    node("Container", {"_name": "cell"}, [label(name, 100)],
                         region=(79, 0, 100, 20)),
                    cell(2, [type_text]),
                    cell(3, [distance]),
                ], region=(0, 0, 440, 20))])]),
            # One container fewer, which shifts every column the other way.
            reading_binding("threeCells", [scanner_window([row_of_cells([
                cell(1, [name]), cell(2, [type_text]),
                cell(3, [distance])])])]),
            # And a row with no children at all, which must not throw.
            reading_binding("noCells", [scanner_window([row_of_cells([])])]),
        ]

    def test_a_longer_row_is_declined(self):
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf fiveCells)",
             "cellOf 0 .type_ (rowsOf fiveCells)",
             "cellOf 0 .distance (rowsOf fiveCells)"],
            definitions=self.definitions())
        self.assertEqual(
            answers, [NOTHING, NOTHING, NOTHING],
            "a row with a container nobody predicted is being read anyway, "
            "which is how a corporation ticker comes to be read as a name")

    def test_a_longer_row_does_not_answer_a_neighbouring_cells_text(self):
        """Named apart from the case above, because it is the harm.

        `Nothing` everywhere is one way to pass that; answering the *wrong*
        string is the failure worth naming, and it is worth asserting that no
        cell came back holding a value that belongs to another column.
        """
        name, type_text, distance = STRUCTURE_ROWS[0]
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf fiveCells)",
             "cellOf 0 .type_ (rowsOf fiveCells)"],
            definitions=self.definitions())
        for answer in answers:
            self.assertNotIn(
                answer,
                [just("EXMPL"), just(name), just(type_text), just(distance)],
                "a cell of an unexpected row shape was filled from a "
                "position that was not measured to hold it")

    def test_a_shorter_row_is_declined(self):
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf threeCells)",
             "cellOf 0 .type_ (rowsOf threeCells)",
             "cellOf 0 .distance (rowsOf threeCells)"],
            definitions=self.definitions())
        self.assertEqual(answers, [NOTHING, NOTHING, NOTHING])

    def test_a_row_with_no_cells_answers_rather_than_throwing(self):
        """The row is still in the list, still carrying its `uiNode`.

        Declining to read the cells is not declining to report the row: a
        consumer counting what is on scan still has to see it, and a parser
        that dropped it would be answering "nothing is there".
        """
        answers = self.repl.strings(
            ["cellOf 0 .name (rowsOf noCells)",
             "cellOf 0 .type_ (rowsOf noCells)",
             "cellOf 0 .distance (rowsOf noCells)"],
            definitions=self.definitions())
        self.assertEqual(answers, [NOTHING, NOTHING, NOTHING])
        [count] = self.repl.strings(
            ["String.fromInt (List.length (rowsOf noCells))"],
            definitions=self.definitions())
        self.assertEqual(
            count, "1",
            "a row whose cells cannot be read is being dropped from the "
            "list, which reads as nothing being on scan")

    def test_the_declined_row_still_carries_the_node_it_came_from(self):
        """`uiNode` is not a cell and is never withheld with them.

        It is what a consumer clicks or measures a position from, and it is
        known whatever the row's internal shape turns out to be.
        """
        [answer] = self.repl.evaluate(
            ["(rowsOf noCells |> List.head"
             " |> Maybe.map (.uiNode >> .uiNode >> .pythonObjectTypeName))"
             ' == Just "DirectionalScanResultEntry"'],
            definitions=self.definitions())
        self.assertTrue(answer)


class TheVendoredCopiesCarryOneRuleTest(unittest.TestCase):
    """All of them, identically -- the policy `CLAUDE.md` states.

    `DirectionalScannerWindow` is a shared type that had **not** diverged
    between the copies before this change: the alias and the window parser were
    byte-identical across every one of them. Landing a read in one copy would
    put a divergence into a block that has none, so this compares the new
    declarations byte for byte and asserts the files still differ otherwise --
    which is what makes "identical here" a property of this block rather than
    an accident of the files being the same.
    """

    def setUp(self):
        self.paths = parser_paths()
        if not self.paths:
            self.skipTest("no vendored parsers under " + APPS_DIR)
        self.sources = {path: source_of(path) for path in self.paths}

    def test_every_app_that_vendors_the_parser_has_it(self):
        """The count comes from the tree, so a new app cannot be missed.

        Asked of the tree rather than written out as a number, for
        `vendored_parser_count`'s own reason: a literal fails on exactly the
        change it should have started covering, and teaches whoever is holding
        the failure to edit the number.
        """
        self.assertEqual(len(self.paths), vendored_parser_count(self.paths),
                         self.paths)
        for path, source in self.sources.items():
            self.assertIn("type alias DirectionalScanResult =\n", source, path)
            self.assertIn(
                "parseDirectionalScanResult :"
                " UITreeNodeWithDisplayRegion -> DirectionalScanResult\n",
                source, path)

    def test_every_copy_has_the_same_one(self):
        reference = self.paths[0]
        for slicer, what in ((result_alias, "what a D-Scan row is"),
                             (result_function, "how a D-Scan row is read")):
            blocks = {path: slicer(source)
                      for path, source in self.sources.items()}
            for path, block in blocks.items():
                self.assertEqual(
                    block, blocks[reference],
                    "%s and %s disagree about %s"
                    % (app_of(path), app_of(reference), what))

    def test_the_copies_still_differ_elsewhere(self):
        """So that "identical here" says something about this block.

        Every one of these files is a diverged copy -- if they were byte-equal
        whole, the case above would hold for reasons that have nothing to do
        with the change.
        """
        distinct = {source for source in self.sources.values()}
        self.assertGreater(
            len(distinct), 1,
            "the vendored parsers are all identical, so comparing one block "
            "across them asserts nothing")

    def test_the_window_carries_parsed_rows_rather_than_bare_nodes(self):
        """The field's own type, in every copy.

        A copy left on `List UITreeNodeWithDisplayRegion` compiles perfectly
        well and hands its bot rows with no cells in them, which is the shape
        this change exists to end.
        """
        for path, source in self.sources.items():
            self.assertIn(
                "    , scanResults : List DirectionalScanResult\n",
                source, path)
            self.assertNotIn(
                "    , scrollNode : Maybe UITreeNodeWithDisplayRegion\n"
                "    , scanResults : List UITreeNodeWithDisplayRegion\n",
                source, path)

    def test_the_window_parser_actually_calls_it(self):
        """Wiring, read out of every copy.

        The executable cases above go through one app. A copy that carries the
        function and never calls it answers with rows whose cells are all
        `Nothing`, on a bot nothing in this file compiles.
        """
        for path, source in self.sources.items():
            start = source.index(
                "parseDirectionalScannerWindowFromUITreeRoot :")
            window_parser = source[start:source.index("\n\n\n", start)]
            self.assertIn(
                "|> List.map parseDirectionalScanResult", window_parser, path)

    def test_the_probe_scanners_header_technique_is_left_alone(self):
        """#458 changes how D-Scan is read and nothing about the probe scanner.

        That window *does* draw a header row, and its cells are matched against
        it. A change that swept the positional read into `parseProbeScanResult`
        would be applying a technique to a window whose own headers are the
        better evidence.
        """
        for path, source in self.sources.items():
            probe = source[source.index("parseProbeScanResult :"):]
            probe = probe[:probe.index("\n\n\n")]
            self.assertIn("entriesHeaders", probe, path)
            self.assertNotIn("parseDirectionalScanResult", probe, path)


class TheParserSaysWhatIsUnverifiedTest(unittest.TestCase):
    """The ship shape is unconfirmed, and the file has to say so.

    Every row behind this change was a structure. That is not a caveat about
    the tests -- it is the case the downstream feature exists for, and somebody
    reading `parseDirectionalScanResult` in six months has to find out from the
    declaration rather than from an issue.
    """

    def setUp(self):
        self.paths = parser_paths()
        if not self.paths:
            self.skipTest("no vendored parsers under " + APPS_DIR)

    def test_the_doc_comment_records_it(self):
        for path in self.paths:
            source = source_of(path)
            start = source.index("{-| Reads a Directional Scanner row")
            doc = source[start:source.index("-}", start)]
            flat = re.sub(r"\s+", " ", doc)
            self.assertIn("Unverified", flat, path)
            self.assertIn("structure", flat, path)
            # The reason the probe scanner's technique does not transfer is
            # what a reader most needs from this comment.
            self.assertIn("no header row", flat, path)


class TheFixturesAreNotOperatorSpecificTest(unittest.TestCase):
    """Nothing in this file names anything real.

    The umbrella issue's standing rule: every name that could identify a
    corporation, alliance, system, structure, character or ship is an operator
    setting with no default in code, and a test fixture is code.
    """

    def test_every_fixture_string_is_marked_fictional(self):
        for name, type_text, distance in STRUCTURE_ROWS:
            self.assertTrue(
                name.startswith("Fictional "),
                "a fixture name that is not obviously invented: " + name)
            self.assertTrue(
                type_text.startswith("Example "),
                "a fixture type that is not obviously invented: " + type_text)
            self.assertRegex(distance, r"^\d+\.\d+ AU$")

    def test_the_fixtures_are_distinguishable_from_one_another(self):
        """Or a swapped column could read as the right answer."""
        names = {name for name, _, _ in STRUCTURE_ROWS}
        types = {type_text for _, type_text, _ in STRUCTURE_ROWS}
        distances = {distance for _, _, distance in STRUCTURE_ROWS}
        self.assertEqual(len(names), len(STRUCTURE_ROWS))
        self.assertEqual(len(distances), len(STRUCTURE_ROWS))
        self.assertFalse(names & types)
        self.assertFalse(types & distances)


if __name__ == "__main__":
    unittest.main()
