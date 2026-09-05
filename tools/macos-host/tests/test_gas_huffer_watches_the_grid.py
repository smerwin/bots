"""The gas huffer's hostile detection: three triggers, and two ways of not
knowing.

Issue #462, under #456. #461 left this bot harvesting a cloud with no way of
noticing anybody arriving. This is the verdict that says whether the ship should
still be there, and five things about it are what the issue is emphatic about.

**Three independent triggers, any one of which fires.** A rat on the overview by
the existing icon-colour rule; any pilot on the overview who Local does not say
is in this fleet, because gas-huffing doctrine is trust nobody and a blue who is
not fleeted still means leave; and any ship on D-Scan whose name does not carry
`friendly-ship-tag`. Each is asked here on a grid where the other two are quiet,
so a rule that had come to depend on another cannot pass.

**Structures are excluded, and that is the whole subtlety of trigger 3.** A
system's own structures sit on D-Scan permanently, carry no ship-naming tag, and
include the home structure this bot deposits at -- so "any untagged D-Scan entry
is a threat" would put this bot in permanent evasion in any inhabited system,
retreating from furniture. Confirmed live for #456: with D-Scan widened, every
row present was a structure. The filter is on the **Type** column against Upwell
structure and deployable hulls, and a D-Scan of nothing but structures has to
read *clean* here.

**Absent evidence reads as hostile, which inverts this repo's usual direction,
and every place it could be undone is asked separately.** An unset
`friendly-ship-tag` makes every ship hostile; a row whose Name cell the parser
answered `Nothing` for is hostile and is **not** defaulted to `""`; a Type cell
the parser could not read is not a structure.

**A reading with no D-Scan window is not a clean grid.** It is "we do not know",
and `gridVerdict` answers a third constructor for it rather than folding it into
either of the others -- because collapsing those is how a bot concludes it is
safe because nothing answered. The status line has to say which of the two it is,
and that sentence is executed rather than asserted by substring.

**A stale scan must not read as a fresh clean one.** The bot carries when a scan
last completed and stops believing one past `dscanStaleAfterIntervals` of the
configured interval, which is the same "we do not know" answer. The bound is
executed at both sides of its boundary and the memory fold that feeds it is run
over whole sessions.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`. Every overview
row, every chat row and every D-Scan row they are asked about is built by
running a UI tree through the **real** `EveOnline.ParseUserInterface`, with a
real overview header row, so what the cases assert on is what the bot would have
been handed rather than a record shaped by hand. Where a case is about a
combination of facts no single fixture can be in at once -- a grid that is both
stale and holding a rat -- the rule is handed the record it takes, which is why
`gridVerdict` takes one.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode and a rule that answered nothing read identically
from outside, which is the shape `prerequisites.elm_json_literal` exists for.

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
    "import Common.EffectOnWindow as EffectOnWindow",
)

# The overview's own header row on this client, read off it on 2026-09-04 and
# quoted in #456. `parseListViewEntry` maps a cell to a header by asking which
# header's span the cell sits inside, so a fixture with no header row produces
# rows with no cells at all -- which is a state several cases below spend their
# time telling apart from a real answer.
OVERVIEW_COLUMNS = (
    ("Icon", 0, 40),
    ("Type", 40, 200),
    ("Name", 240, 200),
    ("Distance", 440, 120),
)

# The colour every rat's icon read on the live client, quoted in CLAUDE.md under
# "Strings and identities read off a live client": red against the white and
# yellow the client draws stargates and the sun in.
RAT_COLOR = {"aPercent": 100, "rPercent": 100, "gPercent": 10, "bPercent": 10}

# What a stargate read on the same client. Present so that the icon rule is
# shown *declining* something rather than only accepting: a rule that had been
# widened to "any icon colour at all" passes every case that only feeds it rats.
STRUCTURE_COLOR = {
    "aPercent": 100, "rPercent": 100, "gPercent": 100, "bPercent": 100}

# The client's own words for a fleet-mate's icon in Local, captured live for
# #224 and recorded in CLAUDE.md. Quoted here byte for byte rather than typed
# from memory, which is the detail a matcher written from memory gets wrong.
FLEETMATE_HINT = "Pilot is in your fleet"

# The D-Scan row shape measured on a live client for #458: four direct
# `Container` children of a `DirectionalScanResultEntry`, at these local
# x-offsets, the first carrying the icon and no text.
DSCAN_CELL_OFFSETS = (0, 19, 179, 309)
DSCAN_CELL_WIDTHS = (19, 160, 130, 100)

# Obviously fictional, which is #456's rule: nothing naming a real corporation,
# structure, system or pilot goes in this repository.
FICTIONAL_TAG = "[EXMPL]"

_address = iter(range(700000, 999999))


def fresh_node(type_name, entries=None, children=(), region=None):
    return node(type_name, entries, children, region)


def label(text, region):
    return fresh_node("EveLabelMedium", {"_setText": text}, region=region)


# -- the overview ------------------------------------------------------------


def overview_row(cells, color=None):
    """One `OverviewScrollEntry`, with a cell only for the columns named.

    `color` is written on an `iconSprite` node under the row's own
    `SpaceObjectIcon`, which is where `parseOverviewEntry` reads it from --
    rather than on the row, which is where a fixture written from the field name
    alone would put it and where the parser would never look.
    """
    y = 100 + overview_row.next_y
    overview_row.next_y += 20
    icon_children = []
    if color is not None:
        icon_children.append(
            fresh_node("Sprite", {"_name": "iconSprite", "_color": color},
                       region=(2, 2, 12, 12)))
    children = [
        fresh_node("SpaceObjectIcon", {"_name": "mainIcon"}, icon_children,
                   region=(0, y, 32, 16)),
    ] + [
        label(cells[column], (x + 4, y, width - 8, 16))
        for column, x, width in OVERVIEW_COLUMNS if column in cells
    ]
    return fresh_node("OverviewScrollEntry", {"_name": "overviewEntry"},
                      children, region=(0, y, 560, 16))


overview_row.next_y = 0


def overview_window(rows):
    """The overview, open, with a real header row over real rows.

    The header container is nested inside the scroll node because
    `parseOverviewWindow` looks for the headers *under* it, and the rows are
    siblings of the scroll rather than children of it -- `OverviewScrollEntry`
    itself contains the word `scroll`, so a row inside would otherwise be picked
    as the scroll node by a rule that takes the first match.
    """
    headers = fresh_node("OverviewHeaders", {"_name": "headers"}, [
        label(column, (x, 60, width, 16))
        for column, x, width in OVERVIEW_COLUMNS
    ], region=(0, 60, 560, 16))
    scroll = fresh_node("OverviewScroll", {"_name": "scroll"}, [headers],
                        region=(0, 60, 560, 16))
    return fresh_node("OverviewWindow", {"_name": "overview"},
                      [scroll] + list(rows), region=(1200, 40, 560, 400))


def rat(name="Fictional Devourer"):
    return overview_row(
        {"Icon": "-", "Type": "Frigate", "Name": name, "Distance": "12 km"},
        color=RAT_COLOR)


def pilot_row(name):
    """An overview row for a player: an ordinary icon colour and a name.

    Nothing on an overview row says it is a player -- five rows were checked live
    for #224 and none carried a standing hint at all -- so what makes this one a
    pilot is its Name appearing in the Local chat fixture beside it.
    """
    return overview_row(
        {"Icon": "-", "Type": "Venture", "Name": name, "Distance": "20 km"},
        color=STRUCTURE_COLOR)


def structure_row(name="Fictional IX - Example Waystation"):
    return overview_row(
        {"Icon": "-", "Type": "Example Citadel", "Name": name,
         "Distance": "84 km"},
        color=STRUCTURE_COLOR)


# -- Local chat --------------------------------------------------------------


def chat_user(name, fleetmate=False):
    """One `XmppChatUserEntry`, with the fleet-mate's own icon where asked.

    `parseChatUserEntry` takes the row's **longest** display text as the name and
    reads the standing hint off a `FlagIconWithState` descendant's `_hint`, which
    is not a display text -- so the icon cannot become the name however it is
    ordered.
    """
    y = 200 + chat_user.next_y
    chat_user.next_y += 18
    children = [label(name, (30, y, 160, 14))]
    if fleetmate:
        children.append(
            fresh_node("FlagIconWithState", {"_hint": FLEETMATE_HINT},
                       region=(10, y, 14, 14)))
    return fresh_node("XmppChatUserEntry", {"_name": "chatUser"}, children,
                      region=(0, y, 200, 18))


chat_user.next_y = 0


def local_chat(users):
    """The Local chat window, in the stack the parser walks down.

    Every one of these nodes is load-bearing: `parseChatWindowStacksFromUITreeRoot`
    matches `ChatWindowStack`, `parseChatWindowStack` matches `XmppChatWindow`
    under it, `localChatWindowFromUserInterface` requires that window's `_name`
    to end `_local`, and `parseChatWindow` finds the userlist by a `_name`
    containing `userlist`. A fixture missing any of them parses to a reading with
    no Local at all, which is exactly the state one case below is *about* and
    which every other case would otherwise be asserting against by accident.
    """
    userlist = fresh_node("Container", {"_name": "userlist"}, list(users),
                          region=(0, 190, 200, 300))
    window = fresh_node("XmppChatWindow", {"_name": "fictional_local"},
                        [userlist], region=(0, 180, 220, 320))
    return fresh_node("ChatWindowStack", {"_name": "chatStack"}, [window],
                      region=(0, 180, 220, 320))


# -- the Directional Scanner -------------------------------------------------


def dscan_cell(index, texts=()):
    return fresh_node(
        "Container", {"_name": "cell"},
        [label(text, (0, 0, DSCAN_CELL_WIDTHS[index], 16)) for text in texts],
        region=(DSCAN_CELL_OFFSETS[index], 0, DSCAN_CELL_WIDTHS[index], 20))


def dscan_row(name, type_text, distance, top=0):
    """A `DirectionalScanResultEntry` in the shape measured for #458.

    `name` of `None` leaves the Name cell empty, which is how a cell the parser
    answers `Nothing` for is produced without changing the row's shape -- the
    other way a row answers `Nothing`, a child count that is not four, is asked
    for separately.
    """
    cells = [
        dscan_cell(0),
        dscan_cell(1, [] if name is None else [name]),
        dscan_cell(2, [] if type_text is None else [type_text]),
        dscan_cell(3, [distance]),
    ]
    return fresh_node("DirectionalScanResultEntry", {}, cells,
                      region=(0, top, 440, 20))


def scanner_window(rows):
    """The `DirectionalScanner` window, with the scroll node the parser wants.

    `parseDirectionalScannerWindowFromUITreeRoot` takes the largest descendant
    whose type name contains "scroll" and looks for the rows under that, so a
    fixture that skipped it parses to a window with no rows -- which reads
    exactly like a scan that found nothing.
    """
    return fresh_node("DirectionalScanner", {"_name": "dscan"}, [
        fresh_node("ScrollControls", {"_name": "scroll"},
                   [row for row in rows], region=(0, 30, 440, 400)),
    ], region=(600, 100, 460, 480))


def dscan_rows(specs):
    return [dscan_row(name, type_text, distance, top=index * 20)
            for index, (name, type_text, distance) in enumerate(specs)]


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


def trust(tag=None):
    return "TrustNobody" if tag is None else "(TrustShipsTagged %s)" % (
        json.dumps(tag))


def scan_age(seconds=0, stale_after=15):
    return "{ secondsSinceScan = %s, staleAfterSeconds = %d }" % (
        "Nothing" if seconds is None else "(Just %d)" % seconds, stale_after)


def evidence_binding(name, reading, tag=None, seconds=0, stale_after=15):
    """A `GridEvidence` built from a real parsed reading, or `Nothing`."""
    return ("%s = %s |> Maybe.map (gridEvidenceFromReading %s %s)" % (
        name, reading, trust(tag), scan_age(seconds, stale_after)))


def evidence(rats="[]", pilots="[]", local_chat_readable=True,
             dscan="(DscanWasRead [])"):
    """A `GridEvidence` written out, since it is a record of plain facts.

    Written here rather than derived from a reading on purpose: these cases are
    about the *combination*, including several a single fixture cannot be in at
    once -- a grid that is simultaneously stale and holding a rat -- and
    `gridVerdict` takes the record precisely so they can be asked for directly.
    `gridEvidenceFromReading` is what builds one from a client and is asked
    separately, off real trees.
    """
    return ("{ ratsOnOverview = %s"
            ", pilotsNotInTheFleet = %s"
            ", localChatIsReadable = %s"
            ", dscan = %s }" % (
                rats, pilots, "True" if local_chat_readable else "False",
                dscan))


def sighting(name="Fictional Venture", type_text="Venture",
             distance="8.3 AU"):
    def cell(value):
        return "Nothing" if value is None else "(Just %s)" % json.dumps(value)

    return "{ name = %s, type_ = %s, distance = %s }" % (
        cell(name), cell(type_text), cell(distance))


class GridRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-grid-repl-")
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
    return open_repl(GridRepl)


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of a row, that it is there.

    Nearly every case below is of the form "this fired the verdict" or "that one
    did not", and a fixture that never decoded produces a reading with no
    overview, no Local and no D-Scan window -- which answers `CannotTell` for the
    right-looking reason, silently and for the wrong one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_rat_icon_colour_comes_back_off_the_real_parser(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.overviewWindows"
            " >> List.concatMap .entries"
            " >> List.map (\\entry -> ( entry.objectName"
            ", iconSpriteHasColorOfRat entry )))"
        ], definitions=[reading_binding("reading", [overview_window([
            rat("Fictional Devourer"),
            structure_row("Fictional IX - Example Waystation"),
        ])])])[0]
        self.assertEqual(
            printed,
            'Just [(Just "Fictional Devourer",True),'
            '(Just "Fictional IX - Example Waystation",False)]')

    def test_local_chat_comes_back_with_the_fleet_hint_on_the_right_row(self):
        printed = self.repl.rendered([
            "reading |> Maybe.andThen"
            " EveOnline.BotFramework.localChatWindowFromUserInterface"
            " |> Maybe.andThen .userlist |> Maybe.map (.visibleUsers"
            " >> List.map (\\user -> ( user.name"
            ", chatUserIsKnownFleetmate user )))"
        ], definitions=[reading_binding("reading", [local_chat([
            chat_user("Fictional Fleetmate", fleetmate=True),
            chat_user("Fictional Stranger"),
        ])])], )[0]
        self.assertEqual(
            printed,
            'Just [(Just "Fictional Fleetmate",True),'
            '(Just "Fictional Stranger",False)]')

    def test_the_dscan_rows_come_back_cell_by_cell(self):
        printed = self.repl.rendered([
            "reading |> Maybe.andThen .directionalScannerWindow"
            " |> Maybe.map dscanSightingsFromWindow"
        ], definitions=[reading_binding("reading", [scanner_window(dscan_rows([
            ("Fictional IX - Example Waystation", "Astrahus", "8.3 AU"),
            (None, "Venture", "1.2 AU"),
        ]))])])[0]
        self.assertEqual(
            printed,
            'Just [{ distance = Just "8.3 AU", name = Just "Fictional IX - '
            'Example Waystation", type_ = Just "Astrahus" },'
            '{ distance = Just "1.2 AU", name = Nothing'
            ', type_ = Just "Venture" }]')

    def test_a_reading_with_no_local_chat_window_says_so(self):
        """The state one whole case below is about, produced as the client
        produces it: everything else parses and Local is simply not there."""
        printed = self.repl.rendered([
            "reading |> Maybe.map (\\parsed ->"
            " ( EveOnline.BotFramework.localChatWindowFromUserInterface parsed"
            " /= Nothing"
            ", parsed.overviewWindows |> List.concatMap .entries"
            " |> List.length ))"
        ], definitions=[reading_binding(
            "reading", [overview_window([rat()])])])[0]
        self.assertEqual(printed, "Just (False,1)")


class TheThreeTriggersFireIndependentlyTest(unittest.TestCase):
    """Each trigger, on a grid where the other two are quiet.

    Independently rather than together, because a rule that had come to read one
    trigger through another -- rats counted off the pilot list, say -- answers
    correctly for every grid that carries both and is wrong for every grid that
    carries one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdict_from(self, children, tag=None, seconds=0, stale_after=15):
        return self.repl.rendered([
            "grid |> Maybe.map gridVerdict"
        ], definitions=[
            reading_binding("reading", children),
            evidence_binding("grid", "reading", tag=tag, seconds=seconds,
                             stale_after=stale_after),
        ])[0]

    def test_a_quiet_grid_reads_clean(self):
        printed = self.verdict_from([
            overview_window([structure_row()]),
            local_chat([chat_user("Fictional Fleetmate", fleetmate=True)]),
            scanner_window(dscan_rows([
                ("Fictional IX - Example Waystation", "Astrahus",
                 "8.3 AU")])),
        ])
        self.assertEqual(printed, "Just GridIsClean")

    def test_a_rat_on_the_overview_fires_on_its_own(self):
        printed = self.verdict_from([
            overview_window([rat("Fictional Devourer")]),
            local_chat([]),
            scanner_window([]),
        ])
        self.assertEqual(
            printed,
            'Just (SomethingIsOnTheGrid ["1 rat(s) on the overview by icon '
            'colour: Fictional Devourer"])')

    def test_a_pilot_who_is_not_in_the_fleet_fires_on_its_own(self):
        printed = self.verdict_from([
            overview_window([pilot_row("Fictional Stranger")]),
            local_chat([chat_user("Fictional Stranger")]),
            scanner_window([]),
        ])
        self.assertEqual(
            printed,
            'Just (SomethingIsOnTheGrid ["1 pilot(s) on the overview who are '
            'not in this fleet: Fictional Stranger"])')

    def test_a_pilot_who_is_in_the_fleet_fires_nothing(self):
        """The other half of the trigger, and the one a rule that had dropped
        the fleet filter would fail: the same overview row, and Local saying it
        is ours."""
        printed = self.verdict_from([
            overview_window([pilot_row("Fictional Fleetmate")]),
            local_chat([chat_user("Fictional Fleetmate", fleetmate=True)]),
            scanner_window([]),
        ])
        self.assertEqual(printed, "Just GridIsClean")

    def test_a_pilot_in_local_who_is_not_on_the_overview_fires_nothing(self):
        """Local names everybody in the system; this trigger is about the
        *grid*. A rule reading the chat list alone would leave every site the
        moment anybody undocked anywhere in the system."""
        printed = self.verdict_from([
            overview_window([structure_row()]),
            local_chat([chat_user("Fictional Stranger")]),
            scanner_window([]),
        ])
        self.assertEqual(printed, "Just GridIsClean")

    def test_an_untagged_ship_on_dscan_fires_on_its_own(self):
        printed = self.verdict_from([
            overview_window([structure_row()]),
            local_chat([]),
            scanner_window(dscan_rows([
                ("Fictional Stranger's Venture", "Venture", "1.2 AU")])),
        ], tag=FICTIONAL_TAG)
        self.assertEqual(
            printed,
            'Just (SomethingIsOnTheGrid ["1 ship(s) on D-Scan that are not '
            'ours: \'Fictional Stranger\'s Venture\'"])')

    def test_a_tagged_ship_on_dscan_fires_nothing(self):
        printed = self.verdict_from([
            overview_window([structure_row()]),
            local_chat([]),
            scanner_window(dscan_rows([
                ("%s Fictional Venture" % FICTIONAL_TAG, "Venture", "1.2 AU")
            ])),
        ], tag=FICTIONAL_TAG)
        self.assertEqual(printed, "Just GridIsClean")

    def test_a_hostile_outranks_a_doubt_where_both_are_there(self):
        """Both mean "not clean", and the hostile is the one an operator can act
        on -- so the verdict names it rather than reporting that the bot cannot
        see."""
        printed = self.repl.rendered([
            "gridVerdict %s" % evidence(
                rats='[ "Fictional Devourer" ]',
                local_chat_readable=False,
                dscan="DscanWindowIsNotInTheReading"),
        ])[0]
        self.assertEqual(
            printed,
            'SomethingIsOnTheGrid ["1 rat(s) on the overview by icon colour: '
            'Fictional Devourer"]')

    def test_only_gridisclean_reads_clean(self):
        """The one line the whole design rests on, asked of all three."""
        clean, hostile, unknown = self.repl.evaluate([
            "gridReadsClean GridIsClean",
            'gridReadsClean (SomethingIsOnTheGrid [ "a reason" ])',
            'gridReadsClean (CannotTellWhetherTheGridIsClean [ "a doubt" ])',
        ])
        self.assertTrue(clean)
        self.assertFalse(hostile)
        self.assertFalse(unknown)


class StructuresAreNotShipsTest(unittest.TestCase):
    """The whole subtlety of trigger 3: furniture is not a threat.

    A system's own structures sit on D-Scan permanently and carry no ship tag,
    the home structure this bot deposits at among them, so a rule that read every
    untagged row as a threat would put this bot into permanent evasion in any
    inhabited system. Every row measured live for #456 was a structure, which is
    what makes the clean answer here the ordinary case rather than an edge one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_dscan_of_nothing_but_structures_reads_clean(self):
        """Built off a real parsed window rather than off records, because this
        is the shape #456 actually measured."""
        printed = self.repl.rendered([
            "grid |> Maybe.map gridVerdict"
        ], definitions=[
            reading_binding("reading", [
                overview_window([structure_row()]),
                local_chat([]),
                scanner_window(dscan_rows([
                    ("Fictional IX - Example Waystation", "Astrahus",
                     "8.3 AU"),
                    ("Fictional IX - Second Example Post", "Raitaru",
                     "12.6 AU"),
                    ("Fictional VII - Example Depot", "Mobile Depot",
                     "0.4 AU"),
                ])),
            ]),
            evidence_binding("grid", "reading", tag=FICTIONAL_TAG),
        ])[0]
        self.assertEqual(printed, "Just GridIsClean")

    def test_every_shipped_marker_reads_as_not_a_ship(self):
        """Each entry in the list, asked with no tag configured -- which is the
        state in which every ship reads hostile, so a marker that had stopped
        matching would show up here as a hostile rather than as a structure."""
        markers = [
            "Astrahus", "Fortizar", "Keepstar", "Raitaru", "Azbel", "Sotiyo",
            "Athanor", "Tatara", "Ansiblex Jump Gate", "Pharolux Cyno Beacon",
            "Tenebrex Cyno Jammer", "Metenox Moon Drill",
            "Amarr Control Tower", "Interbus Customs Office",
            "Mobile Tractor Unit", "Harvestable Cloud",
            # The two variants the substring match is what covers: a faction
            # Fortizar and the largest Upwell hull's own longer name.
            "'Moreau' Fortizar", "Upwell Palatine Keepstar",
        ]
        answers = self.repl.rendered([
            "dscanRowVerdict TrustNobody %s" % sighting(
                name="Fictional Waystation", type_text=marker)
            for marker in markers
        ])
        self.assertEqual(
            answers,
            ['RowIsNotAShip "%s"' % marker for marker in markers])

    def test_a_hull_that_is_not_on_the_list_is_judged_as_a_ship(self):
        """The other side of the filter, and the one that keeps it from being a
        rule that reads everything as furniture."""
        answers = self.repl.rendered([
            "dscanRowVerdict TrustNobody %s" % sighting(
                name="Fictional Ship", type_text=hull)
            for hull in ["Venture", "Astero", "Loki", "Capsule"]
        ])
        self.assertEqual(
            answers,
            ['ShipIsHostile (ShipNameCarriesNoFriendlyTag "Fictional Ship")']
            * 4)

    def test_a_type_cell_the_parser_could_not_read_is_not_a_structure(self):
        """Fail-closed one column along: an unreadable Type falls through to the
        ship branch rather than being read as furniture, and the unreadable Name
        beside it then reads hostile."""
        unreadable_type, both_unreadable = self.repl.rendered([
            "dscanRowVerdict TrustNobody %s" % sighting(
                name="Fictional Ship", type_text=None),
            "dscanRowVerdict TrustNobody %s" % sighting(
                name=None, type_text=None),
        ])
        self.assertEqual(
            unreadable_type,
            'ShipIsHostile (ShipNameCarriesNoFriendlyTag "Fictional Ship")')
        self.assertEqual(
            both_unreadable, "ShipIsHostile ShipNameCouldNotBeRead")

    def test_the_harvestable_cloud_is_the_overview_rules_own_constant(self):
        """The one entry that is this bot's own reason for being there, and the
        one place two spellings of it would be two things to keep in step."""
        self.assertIn(
            "harvestableCloudTypeMarker",
            collapsed(top_level_declarations(bot_source())[
                "notAShipOnDscanTypeMarkers"]))


class AbsentEvidenceReadsHostileTest(unittest.TestCase):
    """The direction that inverts this repo's usual one, at each of the three
    places it could be undone.

    Wrong this way round the bot leaves a site it could have kept working, which
    costs a warp. Wrong the other way it keeps harvesting beside a ship it has
    never seen before -- and the failure is silent, because "nothing hostile on
    the grid" is what the status line prints either way.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_with_no_tag_set_every_ship_on_dscan_reads_hostile(self):
        names = ["Fictional Venture", "", FICTIONAL_TAG + " Fictional Venture"]
        answers = self.repl.rendered([
            "dscanRowVerdict TrustNobody %s" % sighting(
                name=name, type_text="Venture")
            for name in names
        ])
        self.assertEqual(
            answers,
            ['ShipIsHostile (ShipNameCarriesNoFriendlyTag "%s")' % name
             for name in names])

    def test_a_name_the_parser_could_not_read_is_hostile(self):
        """#458 answers `Nothing` rather than `""` precisely so this is
        expressible, and it is expressed as its own reason rather than as the
        untagged one -- a grid full of these is the parser meeting a row shape
        nobody predicted, where a grid full of the other is a grid full of
        strangers."""
        answers = self.repl.rendered([
            "dscanRowVerdict %s %s" % (trust(FICTIONAL_TAG), sighting(
                name=None, type_text="Venture")),
            "dscanRowVerdict TrustNobody %s" % sighting(
                name=None, type_text="Venture"),
        ])
        self.assertEqual(answers, ["ShipIsHostile ShipNameCouldNotBeRead"] * 2)

    def test_an_unreadable_name_is_not_defaulted_to_the_empty_string(self):
        """The mutation this refuses answers identically today, which is why it
        is asked as a pair: an empty name carries no tag either, so a defaulted
        `""` behaves the same and would be one keystroke from a tag that matched
        it. The two reasons are what separate them."""
        unreadable, empty = self.repl.rendered([
            "dscanRowVerdict %s %s" % (trust(FICTIONAL_TAG), sighting(
                name=None, type_text="Venture")),
            "dscanRowVerdict %s %s" % (trust(FICTIONAL_TAG), sighting(
                name="", type_text="Venture")),
        ])
        self.assertEqual(unreadable, "ShipIsHostile ShipNameCouldNotBeRead")
        self.assertEqual(
            empty, 'ShipIsHostile (ShipNameCarriesNoFriendlyTag "")')

    def test_the_tag_is_matched_ignoring_case(self):
        """The client's own casing is not guaranteed -- the name is whatever the
        operator typed into a ship's label -- so a case-sensitive match would
        read a fleet-mate as a stranger and leave a site over one."""
        answers = self.repl.rendered([
            "dscanRowVerdict %s %s" % (trust(FICTIONAL_TAG), sighting(
                name=name, type_text="Venture"))
            for name in ["[exmpl] fictional venture",
                         "[EXMPL] Fictional Venture",
                         "Fictional [Exmpl] Venture"]
        ])
        self.assertEqual(
            answers,
            ['ShipIsOneOfOurs "[exmpl] fictional venture"',
             'ShipIsOneOfOurs "[EXMPL] Fictional Venture"',
             'ShipIsOneOfOurs "Fictional [Exmpl] Venture"'])

    def test_a_chat_row_with_no_standing_hint_is_a_stranger(self):
        """Absent evidence in the one place it decides fleet membership. Read as
        a fleet-mate, an unresolvable chat row would take a pilot *out* of the
        list this bot leaves over."""
        printed = self.repl.rendered([
            "grid |> Maybe.map (.pilotsNotInTheFleet)"
        ], definitions=[
            reading_binding("reading", [
                overview_window([pilot_row("Fictional Stranger")]),
                local_chat([chat_user("Fictional Stranger")]),
            ]),
            evidence_binding("grid", "reading"),
        ])[0]
        self.assertEqual(printed, 'Just ["Fictional Stranger"]')


class NotKnowingIsNotCleanTest(unittest.TestCase):
    """The half that is not about hostiles at all.

    "We do not know" must not read as safe -- collapsing those is how a bot
    concludes it is safe because nothing answered -- so `gridVerdict` answers a
    third constructor and the status line says which of the two states a reading
    is in.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_no_dscan_window_at_all_is_not_a_clean_grid(self):
        verdict, clean = self.repl.rendered([
            "grid |> Maybe.map gridVerdict",
            "grid |> Maybe.map (gridVerdict >> gridReadsClean)",
        ], definitions=[
            reading_binding("reading", [
                overview_window([structure_row()]),
                local_chat([]),
            ]),
            evidence_binding("grid", "reading"),
        ])
        self.assertEqual(
            verdict,
            'Just (CannotTellWhetherTheGridIsClean ["there is no Directional '
            'Scanner window in this reading, so nothing here can see a ship '
            'that is not already on the overview"])')
        self.assertEqual(clean, "Just False")

    def test_scanned_and_empty_reads_differently_from_could_not_scan(self):
        """The distinction the issue names by name. Both readings have nothing
        hostile in them and only one of them is clean, and the two sentences an
        operator gets have to differ."""
        no_window, scanned = self.repl.strings([
            "describeDscanRows DscanWindowIsNotInTheReading",
            "describeDscanRows (DscanWasRead [])",
        ])
        self.assertEqual(
            no_window,
            "D-Scan: no window in this reading, so there are no rows to print.")
        self.assertEqual(
            scanned, "D-Scan: scanned, and nothing at all is on it.")
        self.assertNotEqual(no_window, scanned)

    def test_the_status_line_says_which_of_the_two_it_is(self):
        """Executed rather than asserted by substring over the branch: a clause
        that printed nothing at all would satisfy a substring check on the
        function that builds it."""
        no_window, scanned = self.repl.strings([
            "describeGrid %s" % evidence(dscan="DscanWindowIsNotInTheReading"),
            "describeGrid %s" % evidence(dscan="(DscanWasRead [])"),
        ])
        self.assertIn("CANNOT TELL, which is not the same as clean", no_window)
        self.assertIn("no Directional Scanner window in this reading",
                      no_window)
        self.assertIn("Grid: CLEAN", scanned)
        self.assertNotIn("CANNOT TELL", scanned)

    def test_a_session_that_has_not_scanned_yet_is_not_clean(self):
        verdict = self.repl.rendered([
            "grid |> Maybe.map gridVerdict"
        ], definitions=[
            reading_binding("reading", [
                overview_window([structure_row()]),
                local_chat([]),
                scanner_window([]),
            ]),
            evidence_binding("grid", "reading", seconds=None),
        ])[0]
        self.assertEqual(
            verdict,
            'Just (CannotTellWhetherTheGridIsClean ["the Directional Scanner '
            'has not answered a refresh yet this session"])')

    def test_local_chat_being_unreadable_is_not_a_clean_grid(self):
        """With Local shut nothing in a reading says which overview rows are
        players at all, so trigger 2 cannot fire -- and a trigger that cannot
        fire must not read as a trigger that found nothing."""
        verdict = self.repl.rendered([
            "grid |> Maybe.map gridVerdict"
        ], definitions=[
            reading_binding("reading", [
                overview_window([structure_row()]),
                scanner_window([]),
            ]),
            evidence_binding("grid", "reading"),
        ])[0]
        self.assertEqual(
            verdict,
            'Just (CannotTellWhetherTheGridIsClean ["Local chat is not '
            'readable, so nothing here can tell which overview rows are pilots '
            'at all"])')

    def test_every_doubt_is_reported_rather_than_only_the_first(self):
        printed = self.repl.rendered([
            "gridVerdict %s" % evidence(
                local_chat_readable=False,
                dscan="DscanWindowIsNotInTheReading"),
        ])[0]
        self.assertEqual(printed.count('","'), 1)
        self.assertIn("no Directional Scanner window", printed)
        self.assertIn("Local chat is not readable", printed)


class TheStalenessBoundTest(unittest.TestCase):
    """A stale scan must not read as a fresh clean one.

    The bound is a multiple of `dscan-interval-seconds` rather than a number, so
    an operator who lengthens the interval lengthens the bound with it, and the
    comparison is executed at both sides of its boundary *and* against fixed
    values either side -- a case that only asks about `bound` and `bound - 1`
    passes for any constant at all, including one that admits everything.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_bound_is_a_multiple_of_the_configured_interval(self):
        three, five = self.repl.rendered([
            "dscanStaleAfterSeconds 5",
            "dscanStaleAfterSeconds 12",
        ])
        self.assertEqual(three, "15")
        self.assertEqual(five, "36")
        body = collapsed(top_level_declarations(bot_source())[
            "dscanStaleAfterSeconds"])
        self.assertIn("dscanStaleAfterIntervals", body)

    def test_a_scan_at_the_bound_is_believed_and_one_past_it_is_not(self):
        at_bound, past_bound, well_inside, long_past = self.repl.rendered([
            "dscanState TrustNobody { windowSightings = Just []"
            ", secondsSinceScan = Just 15, staleAfterSeconds = 15 }",
            "dscanState TrustNobody { windowSightings = Just []"
            ", secondsSinceScan = Just 16, staleAfterSeconds = 15 }",
            "dscanState TrustNobody { windowSightings = Just []"
            ", secondsSinceScan = Just 2, staleAfterSeconds = 15 }",
            "dscanState TrustNobody { windowSightings = Just []"
            ", secondsSinceScan = Just 600, staleAfterSeconds = 15 }",
        ])
        self.assertEqual(at_bound, "DscanWasRead []")
        self.assertEqual(well_inside, "DscanWasRead []")
        self.assertEqual(
            past_bound,
            "DscanIsStale { secondsSinceScan = 16, staleAfterSeconds = 15 }")
        self.assertEqual(
            long_past,
            "DscanIsStale { secondsSinceScan = 600, staleAfterSeconds = 15 }")

    def test_a_stale_scan_holding_nothing_is_not_a_clean_grid(self):
        """The case the bound exists for, and the one a bot without it reads as
        clean: the window is open, its rows say nothing is there, and the last
        scan that produced them is old."""
        verdict, clean = self.repl.rendered([
            "grid |> Maybe.map gridVerdict",
            "grid |> Maybe.map (gridVerdict >> gridReadsClean)",
        ], definitions=[
            reading_binding("reading", [
                overview_window([structure_row()]),
                local_chat([]),
                scanner_window([]),
            ]),
            evidence_binding("grid", "reading", seconds=90, stale_after=15),
        ])
        self.assertEqual(
            verdict,
            'Just (CannotTellWhetherTheGridIsClean ["the last Directional Scan '
            'completed 90s ago, past the 15s a scan is believed for"])')
        self.assertEqual(clean, "Just False")

    def test_a_stale_reading_is_not_judged_row_by_row(self):
        """The rows are not read at all past the bound, rather than being read
        and then discounted -- a stale row naming a friendly ship must not be
        able to contribute a `ShipIsOneOfOurs` to anything."""
        printed = self.repl.rendered([
            "dscanState TrustNobody { windowSightings = Just [ %s ]"
            ", secondsSinceScan = Just 99, staleAfterSeconds = 15 }"
            % sighting(name="Fictional Venture", type_text="Venture"),
        ])[0]
        self.assertEqual(
            printed,
            "DscanIsStale { secondsSinceScan = 99, staleAfterSeconds = 15 }")

    def test_the_clock_moves_only_where_a_scan_could_have_arrived(self):
        """`dscanMemoryAfterReading` folded over a session rather than asked
        once, since a rule that is right for one reading and wrong across a
        session is the defect this shape exists to prevent.

        The four readings are the four things that can happen: an ask that got a
        window back, an ask that did not, a reading with a window and no ask
        behind it, and a reading with neither.
        """
        printed = self.repl.rendered([
            "List.foldl dscanMemoryAfterReading initDscanMemory readings",
        ], definitions=[
            "readings ="
            " [ { nowMilliseconds = 1000, refreshAskedInPreviousStep = True"
            ", windowIsInTheReading = True }"
            ", { nowMilliseconds = 2000, refreshAskedInPreviousStep = True"
            ", windowIsInTheReading = False }"
            ", { nowMilliseconds = 3000, refreshAskedInPreviousStep = False"
            ", windowIsInTheReading = True }"
            ", { nowMilliseconds = 4000, refreshAskedInPreviousStep = False"
            ", windowIsInTheReading = False } ]",
        ])[0]
        self.assertEqual(
            printed,
            "{ lastRefreshAskedAtMilliseconds = Just 2000"
            ", lastScanAtMilliseconds = Just 1000 }")

    def test_a_window_with_no_ask_behind_it_never_counts_as_a_scan(self):
        """The half that keeps the bound reachable. The D-Scan window is in
        nearly every reading; if merely reading it counted, the age would be zero
        forever and the bound would be a comparison nothing can meet, which is
        #34's shape."""
        printed = self.repl.rendered([
            "List.foldl dscanMemoryAfterReading initDscanMemory"
            " (List.map (\\at -> { nowMilliseconds = at"
            ", refreshAskedInPreviousStep = False"
            ", windowIsInTheReading = True }) (List.range 1 50))",
        ])[0]
        self.assertEqual(
            printed,
            "{ lastRefreshAskedAtMilliseconds = Nothing"
            ", lastScanAtMilliseconds = Nothing }")

    def test_the_age_is_read_off_the_clock_in_whole_seconds(self):
        never, just_now, older = self.repl.rendered([
            "secondsSinceLastScan { nowMilliseconds = 50000"
            ", dscan = initDscanMemory }",
            "secondsSinceLastScan { nowMilliseconds = 50000"
            ", dscan = { initDscanMemory"
            " | lastScanAtMilliseconds = Just 49500 } }",
            "secondsSinceLastScan { nowMilliseconds = 50000"
            ", dscan = { initDscanMemory"
            " | lastScanAtMilliseconds = Just 20000 } }",
        ])
        self.assertEqual(never, "Nothing")
        self.assertEqual(just_now, "Just 0")
        self.assertEqual(older, "Just 30")


class TheRefreshIsAFloorRatherThanAScheduleTest(unittest.TestCase):
    """The cadence, and what a skipped refresh costs.

    This host stands down for five seconds after any human input, so a refresh
    can simply not go out. The comparison is therefore against when one last
    *went* rather than against a tick the bot has to keep up with, which is what
    makes a skip cost one interval and self-correct.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def due(self, now, asked_at, interval=5):
        return ("dscanRefreshIsDue { nowMilliseconds = %d"
                ", intervalSeconds = %d, dscan = { initDscanMemory"
                " | lastRefreshAskedAtMilliseconds = %s } }" % (
                    now, interval,
                    "Nothing" if asked_at is None else "Just %d" % asked_at))

    def test_never_having_asked_is_due(self):
        """What gets the first scan of a session out on the first reading in
        space rather than an interval into it."""
        self.assertTrue(self.repl.evaluate([self.due(0, None)])[0])

    def test_the_interval_is_a_boundary_and_not_a_window(self):
        early, at, past, much_later = self.repl.evaluate([
            self.due(4999, 0),
            self.due(5000, 0),
            self.due(5001, 0),
            self.due(600000, 0),
        ])
        self.assertFalse(early)
        self.assertTrue(at)
        self.assertTrue(past)
        self.assertTrue(much_later)

    def test_a_longer_interval_asks_less_often(self):
        """The setting reaches the comparison, rather than a constant that
        happens to agree with its default."""
        at_five, at_twelve = self.repl.evaluate([
            self.due(7000, 0, interval=5),
            self.due(7000, 0, interval=12),
        ])
        self.assertTrue(at_five)
        self.assertFalse(at_twelve)

    def test_the_refresh_is_the_only_key_the_press_holds_down(self):
        """`stepPressedExactly` is what the memory update recognises the ask by,
        and it compares the whole key-down sequence -- so a press carrying a
        modifier is not this one, which is what stops `Alt+F1` and the harvester
        keys being read as scans."""
        exact, with_modifier, other_key = self.repl.evaluate([
            "stepPressedExactly directionalScanHotkey"
            " (hotkeyEffects directionalScanHotkey)",
            "stepPressedExactly directionalScanHotkey"
            " (hotkeyEffects [ EffectOnWindow.vkey_MENU"
            ", EffectOnWindow.vkey_V ])",
            "stepPressedExactly directionalScanHotkey"
            " (hotkeyEffects propulsionModuleHotkey)",
        ])
        self.assertTrue(exact)
        self.assertFalse(with_modifier)
        self.assertFalse(other_key)


class TheStatusLinePrintsWhatItJudgedTest(unittest.TestCase):
    """Every judged D-Scan row's own cells, raw.

    #462's own requirement rather than decoration: no D-Scan row for a piloted
    ship has ever been read here, all four rows measured for #458 were
    structures, and the dangerous direction is a corporation ticker landing in
    the Name cell and matching the friendly tag. So the first run that meets a
    ship has to settle the row's shape from the log alone.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_cell_is_printed_including_the_ones_that_did_not_read(self):
        printed = self.repl.strings([
            "describeDscanSightings [ %s, %s ]" % (
                sighting(name="Fictional IX - Example Waystation",
                         type_text="Astrahus", distance="8.3 AU"),
                sighting(name=None, type_text=None, distance="1.2 AU")),
        ])[0]
        self.assertEqual(
            printed,
            "D-Scan rows (Name | Type | Distance, as parsed): "
            "[Fictional IX - Example Waystation | Astrahus | 8.3 AU] "
            "[<unreadable> | <unreadable> | 1.2 AU].")

    def test_an_unreadable_cell_does_not_print_as_an_empty_one(self):
        """The distinction #458's `Maybe` exists for, carried as far as the
        operator: a cell the parser declined and a cell holding nothing must not
        read alike in the one place built to keep them apart."""
        unreadable, empty = self.repl.strings([
            "describeDscanSightings [ %s ]" % sighting(
                name=None, type_text="Venture", distance="1.2 AU"),
            "describeDscanSightings [ %s ]" % sighting(
                name="", type_text="Venture", distance="1.2 AU"),
        ])
        self.assertIn("[<unreadable> | Venture | 1.2 AU]", unreadable)
        self.assertIn("[ | Venture | 1.2 AU]", empty)
        self.assertNotEqual(unreadable, empty)

    def test_the_rows_are_printed_from_the_reading_rather_than_the_verdict(self):
        """Off a real parsed window, so what an operator reads is what the
        parser answered rather than what this file could shape by hand."""
        printed = self.repl.strings([
            "reading |> Maybe.map describeDscanSightingsFromReading"
            " |> Maybe.withDefault \"the fixture did not arrive\"",
        ], definitions=[reading_binding("reading", [scanner_window(dscan_rows([
            ("Fictional IX - Example Waystation", "Astrahus", "8.3 AU"),
        ]))])])[0]
        self.assertEqual(
            printed,
            "D-Scan rows (Name | Type | Distance, as parsed): "
            "[Fictional IX - Example Waystation | Astrahus | 8.3 AU].")

    def test_a_reading_with_no_window_says_so_rather_than_printing_none(self):
        printed = self.repl.strings([
            "reading |> Maybe.map describeDscanSightingsFromReading"
            " |> Maybe.withDefault \"the fixture did not arrive\"",
        ], definitions=[reading_binding(
            "reading", [overview_window([structure_row()])])])[0]
        self.assertEqual(printed, "D-Scan rows: no window in this reading.")

    def test_each_verdict_names_what_it_read(self):
        printed = self.repl.strings([
            "describeDscanRows (DscanWasRead [ %s ])" % ", ".join([
                'RowIsNotAShip "Astrahus"',
                'ShipIsOneOfOurs "%s Fictional Venture"' % FICTIONAL_TAG,
                'ShipIsHostile (ShipNameCarriesNoFriendlyTag'
                ' "Fictional Stranger")',
                "ShipIsHostile ShipNameCouldNotBeRead",
            ]),
        ])[0]
        self.assertEqual(
            printed,
            "D-Scan judged 4 row(s): not a ship (Type 'Astrahus'); "
            "ours ('%s Fictional Venture'); "
            "HOSTILE, no friendly tag ('Fictional Stranger'); "
            "HOSTILE, Name cell unreadable." % FICTIONAL_TAG)


class TheRetreatCoverSaysWhichHalfIsMissingTest(unittest.TestCase):
    """Noticing and leaving are two halves, and only the first has arrived.

    A bot that notices a stranger, says so, and goes on harvesting is worse to
    misread than one that never noticed, so the clause names the half that is
    missing rather than falling silent the moment detection exists.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def cover(self, detection=True, leaving=False, home='Just "Example Refinery"'):
        return ("{ hostileDetectionIsArmed = %s, leavingIsImplemented = %s"
                ", homeStructureName = %s, retreatBookmarkPrefix = \"*\" }" % (
                    "True" if detection else "False",
                    "True" if leaving else "False", home))

    def test_detection_alone_does_not_arm_the_retreat(self):
        with_detection, with_both = self.repl.evaluate([
            "retreatIsUnarmed %s" % self.cover(),
            "retreatIsUnarmed %s" % self.cover(leaving=True),
        ])
        self.assertTrue(with_detection)
        self.assertFalse(with_both)

    def test_the_clause_names_leaving_as_the_missing_half(self):
        printed = self.repl.strings([
            "describeRetreatCover %s" % self.cover(),
        ])[0]
        self.assertIn("RETREAT NOT ARMED", printed)
        self.assertIn("#463", printed)
        self.assertNotIn("nothing in this bot notices a hostile yet", printed)

    def test_a_missing_home_structure_is_still_reported(self):
        printed = self.repl.strings([
            "describeRetreatCover %s" % self.cover(leaving=True, home="Nothing"),
        ])[0]
        self.assertIn("RETREAT NOT ARMED", printed)
        self.assertIn("home-structure-name", printed)

    def test_the_call_site_reads_the_detection_half_rather_than_pinning_it(self):
        """The constant that replaced it is the one naming #463, and it is the
        one a later change flips. A file carrying both as `False` would be a file
        whose clause could not tell an operator which half to go and look at."""
        body = collapsed(top_level_declarations(bot_source())[
            "retreatCoverFromContext"])
        self.assertIn("hostileDetectionIsArmed = True", body)
        self.assertIn("leavingIsImplemented = False", body)


class TheWiringTest(unittest.TestCase):
    """Where the new rules are reached from.

    Read out of the source rather than executed, because each of these is about
    a call site inside a `BotDecisionContext` -- which is exactly the shape #106
    records as unexecutable, and is why every rule above takes a record instead.
    """

    def setUp(self):
        self.declarations = top_level_declarations(bot_source())

    def test_the_refresh_is_asked_before_the_harvest_loop(self):
        """Placement rather than a condition, which is how every other ordering
        in this file is settled: the scan is asked for, and the whole of the
        harvest loop sits in the branch reached when none is due."""
        body = collapsed(self.declarations["huntAndHarvest"])
        self.assertIn("refreshTheDirectionalScanner context", body)
        for later in ("describeCloudSearch", "actOnTheHarvestStep",
                      "warpToTheHuntedSite"):
            with self.subTest(later):
                self.assertLess(
                    body.index("refreshTheDirectionalScanner"),
                    body.index(later))

    def test_the_refresh_declines_rather_than_waiting_when_none_is_due(self):
        """A step on this hot path that answered `Just` unconditionally would
        own the whole bot, which is #257's shape."""
        body = collapsed(self.declarations["refreshTheDirectionalScanner"])
        self.assertIn("dscanRefreshIsDue", body)
        self.assertIn("else Nothing", body)
        self.assertNotIn("waitForProgressInGame", body)

    def test_the_memory_update_records_the_ask_and_the_window(self):
        body = collapsed(self.declarations["updateMemoryForNewReadingFromGame"])
        self.assertIn("dscanMemoryAfterReading", body)
        self.assertIn("stepPressedExactly directionalScanHotkey", body)
        self.assertIn("context.timeInMilliseconds", body)
        self.assertIn("directionalScannerWindow /= Nothing", body)

    def test_the_status_line_carries_the_verdict_and_the_raw_rows(self):
        body = collapsed(self.declarations["statusTextFromState"])
        for clause in ("describeGrid", "describeDscanSightingsFromReading",
                       "describeDscanCadence"):
            self.assertIn(clause, body)

    def test_the_verdict_is_settled_once_and_read_by_name(self):
        """#102's rule: one fact settled in one place and read in another cannot
        come to disagree, and the way it would fail here is a status line
        reporting a clean grid a retreat was acting on."""
        source = collapsed(bot_source())
        self.assertEqual(source.count("gridVerdict evidence ="), 1)
        self.assertIn("gridEvidenceFromContext context", source)


class TheParserIsNotTouchedTest(unittest.TestCase):
    """This change reads the D-Scan rows #458 landed and adds nothing to the
    parser.

    `EveOnline/ParseUserInterface.elm` is vendored once per app and the gas
    huffer's copy is byte-identical to `eve-online-wingman`'s. A hostile-detection
    rule that needed a parser change would be an eight-copy concern (#467) rather
    than a one-file edit, so the absence of one is asserted rather than left to
    be noticed in review.
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

    1.  `dscanRowVerdict`'s `Nothing` name branch defaulted to `""` --
        `ShipIsHostile (ShipNameCarriesNoFriendlyTag "")` --
        `AbsentEvidenceReadsHostileTest
        .test_an_unreadable_name_is_not_defaulted_to_the_empty_string`.
    2.  `dscanState`'s `Nothing` window branch answering `DscanWasRead []` --
        `NotKnowingIsNotCleanTest.test_no_dscan_window_at_all_is_not_a_clean_grid`.
    3.  the structure filter dropped, so `dscanTypeIsNotAShip` answers `False`
        for everything -- `StructuresAreNotShipsTest
        .test_a_dscan_of_nothing_but_structures_reads_clean` and
        `test_every_shipped_marker_reads_as_not_a_ship`.
    4.  the structure filter widened to answer `True` for everything --
        `StructuresAreNotShipsTest
        .test_a_hull_that_is_not_on_the_list_is_judged_as_a_ship`.
    5.  an unreadable Type read as a structure (`Maybe.withDefault ""` before the
        marker match, with `""` added to the markers) -- `StructuresAreNotShipsTest
        .test_a_type_cell_the_parser_could_not_read_is_not_a_structure`.
    6.  `shipReadsFriendly` reached with `String.contains` rather than
        `stringContainsIgnoringCase` -- `AbsentEvidenceReadsHostileTest
        .test_the_tag_is_matched_ignoring_case`.
    7.  `chatUserIsKnownFleetmate`'s `Nothing` branch answering `True` --
        `AbsentEvidenceReadsHostileTest
        .test_a_chat_row_with_no_standing_hint_is_a_stranger`.
    8.  the fleet filter dropped from `pilotsOnTheOverviewNotInTheFleet` --
        `TheThreeTriggersFireIndependentlyTest
        .test_a_pilot_who_is_in_the_fleet_fires_nothing`.
    9.  `pilotsOnTheOverviewNotInTheFleet` answering the chat list rather than
        the overview rows in it -- `TheThreeTriggersFireIndependentlyTest
        .test_a_pilot_in_local_who_is_not_on_the_overview_fires_nothing`.
    10. `localChatIsReadable` pinned `True` -- `NotKnowingIsNotCleanTest
        .test_local_chat_being_unreadable_is_not_a_clean_grid`.
    11. `gridVerdict`'s doubts dropped, so an unknown reads clean --
        `NotKnowingIsNotCleanTest.test_no_dscan_window_at_all_is_not_a_clean_grid`.
    12. `gridReadsClean` answering `True` for `CannotTellWhetherTheGridIsClean`
        as well -- `TheThreeTriggersFireIndependentlyTest
        .test_only_gridisclean_reads_clean`.
    13. the staleness comparison moved by one (`<=` for `<`) --
        `TheStalenessBoundTest
        .test_a_scan_at_the_bound_is_believed_and_one_past_it_is_not`.
    14. `dscanStaleAfterSeconds` written as a bare `15` --
        `TheStalenessBoundTest
        .test_the_bound_is_a_multiple_of_the_configured_interval`.
    15. `dscanMemoryAfterReading` recording a scan on any reading with a window,
        with no ask behind it -- `TheStalenessBoundTest
        .test_a_window_with_no_ask_behind_it_never_counts_as_a_scan`.
    16. `dscanRefreshIsDue`'s `Nothing` branch answering `False`, so a session
        never takes its first scan -- `TheRefreshIsAFloorRatherThanAScheduleTest
        .test_never_having_asked_is_due`.
    17. `dscanRefreshIsDue` comparing against a constant rather than the setting
        -- `TheRefreshIsAFloorRatherThanAScheduleTest
        .test_a_longer_interval_asks_less_often`.
    18. the refresh placed *after* the harvest loop -- `TheWiringTest
        .test_the_refresh_is_asked_before_the_harvest_loop`.
    19. `describeDscanSightings` printing an unreadable cell as `""` --
        `TheStatusLinePrintsWhatItJudgedTest
        .test_an_unreadable_cell_does_not_print_as_an_empty_one`.
    20. `retreatCoverFromContext` left with `hostileDetectionIsArmed = False` --
        `TheRetreatCoverSaysWhichHalfIsMissingTest
        .test_the_call_site_reads_the_detection_half_rather_than_pinning_it`.
    21. `leavingIsImplemented` dropped from `retreatIsUnarmed`, so the clause
        reports an armed retreat -- `TheRetreatCoverSaysWhichHalfIsMissingTest
        .test_detection_alone_does_not_arm_the_retreat`.
    22. `iconSpriteHasColorOfRat`'s `Nothing` branch answering `True`, so every
        unreadable icon is a rat -- `TheThreeTriggersFireIndependentlyTest
        .test_a_quiet_grid_reads_clean`.
    """

    def test_this_file_names_the_mutations_it_was_graded_against(self):
        self.assertGreaterEqual(
            self.__doc__.count("--"), 20,
            "the mutation list is the record of how these cases were graded")


if __name__ == "__main__":
    unittest.main()
