"""Tests for the Locations window being found under either of its type names.

Issue #457. `parseLocationsWindowFromUITreeRoot` filtered on
`pythonObjectTypeName == "LocationsWindow"` in every vendored copy, and the
client the findings for #456 were read off renders that window as
`StandaloneBookmarkWnd` and carries **no** node named `LocationsWindow`
anywhere in the tree. So `locationsWindow` read `Nothing` on every reading
while the window was open, populated with 20 bookmarks and captioned
`Locations in <system>`.

It fails in this repo's signature direction -- absent rather than wrong -- and
it is not only a prerequisite for a new app: `eve-online-mining-bot`'s
`useContextMenuOnLocationWithMatchingName` reads
`context.readingFromGameClient.locationsWindow.placeEntries` for its
`mining-site` and `unload-station-name` settings, so on this client that read
has been answering `Nothing` for as long as the code has existed and both
settings were inert by that path.

**Both names are matched, not one replacing the other.** The `LocationsWindow`
name came from a session recording shared upstream, so it is evidence about
some build rather than a mistake, and this parser is vendored into every app.
That is the shape the parser already uses for the overview window's own
`OverView` / `OverviewWindow` / `OverviewWindowOld`.

**The row logic underneath is untouched**, which the issue asks for explicitly:
`parseLocationsWindow` filters rows with `String.contains "PlaceEntry"`, which
matches this client's real row type exactly, and
`parseLocationsWindowPlaceEntry` reads the single `EveLabelMedium` whose text
carries the columns joined by `<t>` tags. `TheRowParsingIsUnchangedTest`
executes that against the live shape and pins the two declarations.

The parser is executed through the real `EveOnline.ParseUserInterface` --
readings are built as raw UI trees and decoded with
`decodeMemoryReadingFromString` and `parseUserInterfaceFromUITree`, the way
`test_route_marker_num_jumps.py` does -- via the shared harness in
`prerequisites.py`. Nothing here reads a live game client or drives a bot, and
every name in every fixture is fictional.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import itertools
import os
import re
import unittest

from prerequisites import (ElmRepl, REPO_DIR, elm_json_literal, open_repl,
                           vendored_parser_count)

EVE_APPS_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online")

MINING_BOT_DIR = os.path.join(EVE_APPS_DIR, "eve-online-mining-bot")
MINING_BOT_ELM = os.path.join(MINING_BOT_DIR, "Bot.elm")

#: The name this client draws the window under, and the name the upstream
#: recording drew it under. Read out of the parser rather than restated, so a
#: case cannot go on passing against a literal only the test still believes in.
THIS_CLIENT_TYPE_NAME = "StandaloneBookmarkWnd"
UPSTREAM_TYPE_NAME = "LocationsWindow"

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

_address = itertools.count(500000)


def parser_files():
    return sorted(glob.glob(os.path.join(
        EVE_APPS_DIR, "*", "EveOnline", "ParseUserInterface.elm")))


def app_of(parser_path):
    return os.path.basename(os.path.dirname(os.path.dirname(parser_path)))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    return " ".join(text.split())


def declaration(name, source):
    """`name`'s type annotation and body, up to the next top-level gap."""
    match = re.search(r"^%s\s*:.*?(?=\n\n\n|\Z)" % re.escape(name),
                      source, re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


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


def row_text(index):
    """One row's tag-joined blob, in the client's own `<t>`-separated shape.

    Every name here is fictional. `parseLocationsWindowPlaceEntry`'s own
    comment records the shape of a real observed row; only the shape matters
    here, so the names are placeholders.
    """
    return "<t>Refinery<t>0<t>AA1-BB<t>Placeholder Depot %d" % index


def place_entry(index, y, second_text=None):
    """One `PlaceEntry`, with the two children the live first row had.

    Measured on the client for #457: the first row's children are exactly
    `['EveLabelMedium', 'Icon']` and its text comes back as one tag-joined
    blob off the label.

    `second_text` adds a *wider* label carrying different text, which is **not**
    the live shape and is only ever passed by the case that exercises the row
    parser's tie-break -- it sorts every contained text by display area and
    takes the smallest. With one text a row the sort cannot be observed at all,
    so a mutation to it would pass unnoticed against a faithful fixture.
    """
    children = [node("EveLabelMedium", {"_setText": row_text(index)},
                     region=(20, y, 300, 18))]
    if second_text is not None:
        children.append(node("EveLabelMedium", {"_setText": second_text},
                             region=(10, y, 310, 19)))
    children.append(node("Icon", {}, region=(2, y, 16, 16)))
    return node("PlaceEntry", {}, children, region=(0, y, 320, 20))


def locations_tree(window_type_names, row_count=20, second_text=None):
    """A `UIRoot` holding one window per name given, each with `row_count` rows.

    The subtree mirrors what was counted live with 20 bookmarks in the window:
    `PlaceEntry: 20  EveLabelMedium: 21  Icon: 20  ColumnHeader: 3  Scroll: 1`
    -- the twenty-first label being the caption, which sits outside every row
    and so must not become a place entry.
    """
    windows = []
    for window_index, type_name in enumerate(window_type_names):
        top = 100 + window_index * 400
        caption = node(
            "EveLabelMedium", {"_setText": "Locations in AA1-BB"},
            region=(4, top, 200, 18))
        headers = [
            node("ColumnHeader", {"_setText": name},
                 region=(20 + column * 100, top + 20, 100, 16))
            for column, name in enumerate(("Name", "Distance", "Location"))
        ]
        rows = [place_entry(index, top + 40 + index * 20, second_text)
                for index in range(row_count)]
        scroll = node("Scroll", {}, rows, region=(0, top + 40, 320, 400))
        windows.append(node(
            type_name, {}, [caption] + headers + [scroll],
            region=(0, top, 340, 460)))
    return node("UIRoot", {}, windows, region=(0, 0, 1920, 1080))


def reading_binding(name, window_type_names, row_count=20, second_text=None):
    """A binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what the cases assert on is what the bot
    would have been handed rather than a record written out by hand. See
    `elm_json_literal`'s own doc comment for why the literal is built there and
    not with a triple-quoted string.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, elm_json_literal(
                   locations_tree(window_type_names, row_count, second_text)))


WINDOW = "(reading |> Maybe.andThen .locationsWindow)"


class MiningBotRepl(ElmRepl):
    """The app whose live consumer this un-breaks.

    The parser block is byte-identical across every copy -- `TheVendoredCopies
    Test` is what says so -- so any app would execute the same parse. This one
    is chosen because it is the app with a decision reading `locationsWindow`.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "locations-window-repl-")
        kwargs.setdefault("app_dir", MINING_BOT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class ReplCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(MiningBotRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def found_window_type(self, window_type_names, row_count=20):
        """The type name of the window the parser picked, or `Nothing`."""
        answers = self.repl.values(
            ["%s |> Maybe.map (.uiNode >> .uiNode >> .pythonObjectTypeName)"
             " |> Debug.toString" % WINDOW],
            r'"(.*?)"\s*: String',
            definitions=[reading_binding(
                "reading", window_type_names, row_count)])
        return answers[0]

    def place_entry_count(self, window_type_names, row_count=20):
        answers = self.repl.values(
            ["%s |> Maybe.map (.placeEntries >> List.length)"
             " |> Debug.toString" % WINDOW],
            r'"(.*?)"\s*: String',
            definitions=[reading_binding(
                "reading", window_type_names, row_count)])
        return answers[0]


class TheWindowTypeNameTest(ReplCase):
    """Which nodes `parseLocationsWindowFromUITreeRoot` will accept."""

    def test_this_client_s_window_is_found(self):
        """The whole bug: a tree carrying only `StandaloneBookmarkWnd`."""
        self.assertEqual(
            self.found_window_type([THIS_CLIENT_TYPE_NAME]),
            "Just \\\"%s\\\"" % THIS_CLIENT_TYPE_NAME)

    def test_the_upstream_window_is_still_found(self):
        """Matching both names, not replacing one with the other -- a build
        that draws the recorded name must not be broken by this."""
        self.assertEqual(
            self.found_window_type([UPSTREAM_TYPE_NAME]),
            "Just \\\"%s\\\"" % UPSTREAM_TYPE_NAME)

    def test_a_window_of_neither_name_is_not_a_locations_window(self):
        """The control that stops "match everything" passing the two above.

        `InventoryPrimary` is a real window this client draws, carries rows and
        a caption, and is emphatically not the Locations window.
        """
        self.assertEqual(
            self.found_window_type(["InventoryPrimary"]), "Nothing")

    def test_a_tree_with_no_such_window_reads_nothing(self):
        self.assertEqual(self.found_window_type([]), "Nothing")

    def test_both_names_at_once_still_yield_one_window(self):
        """`List.head` is unchanged: the filter widened, the pick did not."""
        self.assertEqual(
            self.found_window_type(
                [THIS_CLIENT_TYPE_NAME, UPSTREAM_TYPE_NAME]),
            "Just \\\"%s\\\"" % THIS_CLIENT_TYPE_NAME)


class TheRowParsingIsUnchangedTest(ReplCase):
    """#457 says explicitly not to touch the rows. This is what says it holds.

    Both halves: the rows are executed off the window found under the new name,
    and the two row declarations are read out of the source.
    """

    def test_the_twenty_bookmarks_measured_live_all_become_place_entries(self):
        self.assertEqual(
            self.place_entry_count([THIS_CLIENT_TYPE_NAME], row_count=20),
            "Just 20")

    def test_the_same_rows_under_the_upstream_name_parse_identically(self):
        self.assertEqual(
            self.place_entry_count([UPSTREAM_TYPE_NAME], row_count=20),
            "Just 20")

    def test_an_empty_window_has_no_place_entries(self):
        """Distinct from the window being absent, which reads `Nothing`."""
        self.assertEqual(
            self.place_entry_count([THIS_CLIENT_TYPE_NAME], row_count=0),
            "Just 0")

    def test_the_row_text_arrives_as_the_client_s_tag_joined_blob(self):
        """Byte for byte, tags and all -- a `mainText` a consumer matches on."""
        answers = self.repl.values(
            ["%s |> Maybe.map (.placeEntries >> List.map .mainText)"
             " |> Maybe.withDefault [] |> List.take 2 |> Debug.toString"
             % WINDOW],
            r'"(.*?)"\s*: String',
            definitions=[reading_binding(
                "reading", [THIS_CLIENT_TYPE_NAME], row_count=2)])
        self.assertEqual(
            answers[0],
            "[%s]" % ",".join(
                '\\"%s\\"' % row_text(index) for index in range(2)))

    def test_a_row_with_two_texts_still_yields_the_smallest_one(self):
        """The tie-break, which one text a row cannot exercise.

        A wider label carrying different text is not what was measured live --
        see `place_entry` -- and is here so that a change to the sort is
        caught. `parseLocationsWindowPlaceEntry` sorts every contained text by
        display area and takes the smallest, so the wider one must lose.
        """
        answers = self.repl.values(
            ["%s |> Maybe.map (.placeEntries >> List.map .mainText)"
             " |> Maybe.withDefault [] |> Debug.toString" % WINDOW],
            r'"(.*?)"\s*: String',
            definitions=[reading_binding(
                "reading", [THIS_CLIENT_TYPE_NAME], row_count=1,
                second_text="a wider label nobody wants")])
        self.assertEqual(answers[0], "[\\\"%s\\\"]" % row_text(0))

    def test_the_caption_outside_the_rows_is_not_a_place_entry(self):
        """The twenty-first `EveLabelMedium` counted live is the caption, and
        the row filter is what keeps it out of `placeEntries`."""
        answers = self.repl.evaluate(
            ["%s |> Maybe.map (.placeEntries >> List.map .mainText)"
             " |> Maybe.withDefault []"
             " |> List.any (String.contains \"Locations in\")" % WINDOW],
            definitions=[reading_binding(
                "reading", [THIS_CLIENT_TYPE_NAME], row_count=3)])
        self.assertFalse(answers[0])

    def test_the_row_filter_still_matches_on_placeentry(self):
        body = collapsed(declaration(
            "parseLocationsWindow",
            source_of(os.path.join(
                MINING_BOT_DIR, "EveOnline", "ParseUserInterface.elm"))))
        self.assertIn('String.contains "PlaceEntry"', body)

    def test_the_row_parser_still_reads_the_smallest_contained_text(self):
        body = collapsed(declaration(
            "parseLocationsWindowPlaceEntry",
            source_of(os.path.join(
                MINING_BOT_DIR, "EveOnline", "ParseUserInterface.elm"))))
        self.assertIn("getAllContainedDisplayTextsWithRegion", body)
        self.assertIn("areaFromDisplayRegion", body)
        # Quoted, because `LocationsWindowPlaceEntry` is this declaration's own
        # return type: what must not appear here is a window *type name*.
        self.assertNotIn('"%s"' % THIS_CLIENT_TYPE_NAME, body)
        self.assertNotIn('"%s"' % UPSTREAM_TYPE_NAME, body)


class TheVendoredCopiesTest(unittest.TestCase):
    """The parser policy: this block was identical across every copy, so a
    change to one alone would introduce a divergence into a block that has none.

    Named for the property rather than for a count. CLAUDE.md and #457 both say
    "six copies" and there are **seven** apps vendoring the parser today, which
    is exactly why `vendored_parser_count` derives the number from the tree --
    a literal goes red on the change it should have started covering.
    """

    def blocks(self, name):
        return {app_of(path): declaration(name, source_of(path))
                for path in parser_files()}

    def test_every_app_with_a_bot_vendors_the_parser(self):
        """The guard in front of "every copy has it", so a discovery that
        found a subset cannot pass vacuously."""
        paths = parser_files()
        self.assertEqual(len(paths), vendored_parser_count(paths))
        self.assertGreater(len(paths), 1)

    def test_the_window_lookup_is_identical_across_every_copy(self):
        blocks = self.blocks("parseLocationsWindowFromUITreeRoot")
        first_app, first_block = sorted(blocks.items())[0]
        for app, block in sorted(blocks.items()):
            self.assertEqual(
                block, first_block,
                "%s's parseLocationsWindowFromUITreeRoot differs from %s's"
                % (app, first_app))

    def test_every_copy_matches_both_type_names(self):
        for app, block in sorted(
                self.blocks("parseLocationsWindowFromUITreeRoot").items()):
            collapsed_block = collapsed(block)
            self.assertIn('"%s"' % THIS_CLIENT_TYPE_NAME, collapsed_block, app)
            self.assertIn('"%s"' % UPSTREAM_TYPE_NAME, collapsed_block, app)
            self.assertNotIn(
                '(==) "%s"' % UPSTREAM_TYPE_NAME, collapsed_block, app)

    def test_the_row_declarations_are_identical_across_every_copy(self):
        for name in ("parseLocationsWindow", "parseLocationsWindowPlaceEntry"):
            blocks = self.blocks(name)
            first_app, first_block = sorted(blocks.items())[0]
            for app, block in sorted(blocks.items()):
                self.assertEqual(
                    block, first_block,
                    "%s's %s differs from %s's" % (app, name, first_app))


class TheConsumerThisUnBreaksTest(unittest.TestCase):
    """Why this is a live bug in a shipped app and not only a prerequisite.

    Read out of the source rather than executed: what is being checked is that
    `eve-online-mining-bot` still reaches for the field the parse now fills, so
    that a later change severing that read is a decision somebody argues for.
    """

    def test_the_mining_bot_still_reads_the_locations_window(self):
        body = collapsed(declaration(
            "useContextMenuOnLocationWithMatchingName",
            source_of(MINING_BOT_ELM)))
        self.assertIn("context.readingFromGameClient.locationsWindow", body)
        self.assertIn("locationsWindow.placeEntries", body)
        self.assertIn(".mainText", body)


if __name__ == "__main__":
    unittest.main()
