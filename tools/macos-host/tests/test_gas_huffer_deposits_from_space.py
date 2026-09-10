"""The gas huffer's in-space deposit: select, Access Dropbox, drag, Transfer.

Issue #476, under #456, and it is #464's deposit with the dock taken out of the
middle of it. What the docked sequence pays for is `DockingRunIn` -- the run-in
whose own comment records keeping a mission runner 17 km off a station for eight
minutes -- then the lobby, the hangar, the drag and the undock. The in-space
transfer removes all of that and leaves a warp and a drag.

**Four things this file is emphatic about, each of which is a way the change
could have been wrong.**

**The window is read by name and never by position.** `DropboxWnd`,
`TransferInputContainer`, `inputScroll`, `transferBtn`, `transferToLabel` and
`numItemsLabel` were captured at particular coordinates on one reading, and
those coordinates are one reading's. Every fixture here is drawn at *different*
coordinates from the capture, so a rule that had learned a position would fail
rather than pass.

**`numItemsLabel` is not a staged count, and reading it as one concludes a
successful drag failed.** Measured live on 2026-09-10: with the window open and
nothing staged it read `2 Items` -- the hold's own two stacks -- and after one
stack was staged it read `1 Item`. It counts *down*. So the staged count is
`inputScroll`'s own contents and the label is printed and decided on by nothing,
which two cases assert in both directions.

**The transfer button says whether pressing it will do anything, in its own
texts.** Disabled it carries two, `Nothing to transfer` and `Transfer`; enabled
it carries only `Transfer`. That is the client's own enabled state, and it is
one of the two independent readings `PressTheTransferButton` is gated on -- the
other being the staged stacks. Neither alone commits a transfer.

**The docked deposit is still the fallback and the retreat still outranks the
whole thing.** #476 carries both constraints over from #464 and both are
asserted: a structure offering no dropbox, a ship not yet close enough and a
window this bot cannot read all fall through to the docked sequence, and a grid
that stops reading clean takes the ship out of a transfer exactly as it takes it
out of a docking run-in.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`. Every window,
label, button, panel and overview row they are asked about is built by running a
UI tree through the **real** `EveOnline.ParseUserInterface`, so what the cases
assert on is what the bot would have been handed -- and **no parser change was
made**, which is the point of reaching for `uiTree` rather than editing eight
vendored copies (#467). Where a case is about a combination no single fixture can
be in at once, the rule is handed the record it takes, which is why `depositStep`
takes one.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode and a rule that answered nothing read identically from
outside.

Confirmed by mutation, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client, a running bot, or the recorded runs. Every
name in it is fictional, which is #456's rule.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import unittest

from prerequisites import elm_json_literal
from test_gas_huffer_scaffold import (
    bot_source, collapsed, node, top_level_declarations)
from test_gas_huffer_deposits_the_hold import (
    FICTIONAL_STRUCTURE, GAUGE_FULL, evasion_situation, game_log, repl,
    ship_inventory, situation, tree_with)

# A second structure, so "the window names the one the panel is showing" is a
# question with two possible answers rather than one. Fictional, as #456 requires.
ANOTHER_STRUCTURE = "Fictional II - Example Depot"

# The client's own label texts, as the 2026-09-09 capture recorded them.
DESTINATION_LABEL = "Structure to transfer to:%s" % FICTIONAL_STRUCTURE
DROP_HINT = "Drop items here to deposit to your Item Hangar"

# The transfer button's two states, measured 2026-09-10. Disabled it carries
# both texts; enabled it carries only the second.
TRANSFER_DISABLED = ["Nothing to transfer", "Transfer"]
TRANSFER_ENABLED = ["Transfer"]

# The live in-space transfer's own confirmation. Note the plural verb and the
# absent system: #456 recorded `N item(s) was moved to your hangar in <system> -
# <structure>` and this is what the client wrote on 2026-09-10.
IN_SPACE_CONFIRMATION = "2 items were moved to your hangar in %s" % (
    FICTIONAL_STRUCTURE)


# -- the transfer window -----------------------------------------------------


def named_label(name, text, region):
    """One `EveLabelMedium` carrying the client's own `_name`, which is how
    every label in this window is found."""
    return node("EveLabelMedium", {"_name": name, "_setText": text},
                region=region)


def staged_stack(name, index=0):
    """One stack sitting inside `inputScroll`, in the shape the hold's own
    stacks were read in: an `InvItem` whose `_name` reads `ItemEntry_<id>`."""
    return node("InvItem", {"_name": "ItemEntry_%d" % (30000 + index)},
                [named_label("itemLabel", name, (2, 30, 60, 12))],
                region=(800 + index * 70, 520, 64, 64))


def dropbox_window(destination=DESTINATION_LABEL, staged=(),
                   transfer_texts=None, item_count="0 Items",
                   with_drop_target=True, with_transfer_button=True,
                   with_cancel=True, valid_range=10000.0, left=200, top=100):
    """`DropboxWnd`, in the shape the live press opened.

    **Drawn somewhere other than where the capture recorded it**, on purpose:
    the capture put it at (760, 406) and every part of it at a fixed offset from
    that, and nothing in this bot may have learned those numbers. `left` and
    `top` move the whole thing, and the cases below use the default rather than
    the capture's coordinates.

    `with_drop_target`, `with_transfer_button` and `with_cancel` each remove one
    part, because a window missing one is a distinct answer rather than a window
    to act on with what was found.
    """
    if transfer_texts is None:
        transfer_texts = TRANSFER_DISABLED
    children = [
        named_label("transferToLabel", destination,
                    (left + 20, top + 30, 300, 16))
        if destination is not None else
        node("Container", {"_name": "noDestination"},
             region=(left + 20, top + 30, 300, 16)),
        named_label("numItemsLabel", item_count,
                    (left + 20, top + 50, 120, 16)),
        named_label("totalPriceLabel", "0 ISK Est. price",
                    (left + 160, top + 50, 160, 16)),
    ]
    if with_drop_target:
        scroll = node(
            "ScrollContainer", {"_name": "inputScroll"},
            [named_label("inputHint", DROP_HINT,
                         (left + 30, top + 110, 320, 16))]
            + list(staged),
            region=(left + 24, top + 100, 340, 220))
        children.append(node("TransferInputContainer", {"_name": "inputInfo"},
                             [scroll],
                             region=(left + 22, top + 96, 356, 238)))
    if with_transfer_button:
        children.append(node(
            "Button", {"_name": "transferBtn"},
            [named_label("transferText%d" % index, text,
                         (left + 300, top + 350 + index * 4, 120, 16))
             for index, text in enumerate(transfer_texts)],
            region=(left + 295, top + 344, 100, 28)))
    if with_cancel:
        children.append(node(
            "Button", {"_name": "cancelBtn"},
            [named_label("cancelText", "Cancel",
                         (left + 26, top + 350, 80, 16))],
            region=(left + 22, top + 344, 100, 28)))
    entries = {"_name": "dropboxWnd",
               "_Window__caption": "Upwell Cargo Deposit"}
    if valid_range is not None:
        entries["validRange"] = valid_range
    return node("DropboxWnd", entries, children,
                region=(left, top, 400, 400))


def reading_binding(name, children):
    """A `let` binding of `name` to a real parsed reading.

    The same construction the deposit's own file uses, restated here rather than
    imported because that module keeps it private to its own fixtures; it goes
    through `elm_json_literal` for #174's reason -- a fixture that never arrived
    and a rule that answered nothing read identically from outside.
    """
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree" % (
                name, elm_json_literal(tree_with(children))))


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of the window, that it is there.

    Every case below is of the form "the window said so", and a fixture that
    never decoded produces a reading with no `uiTree` worth walking -- which
    answers `Nothing` for the right-looking reason, silently and for the wrong
    one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_reading_decodes_and_carries_the_window(self):
        decoded, found = self.repl.rendered(
            ["reading /= Nothing",
             "reading |> Maybe.andThen dropboxWindowFromReading |> (/=) Nothing"],
            definitions=[reading_binding("reading", [dropbox_window()])])
        self.assertEqual(decoded, "True")
        self.assertEqual(found, "True")

    def test_a_reading_with_no_window_answers_nothing(self):
        """The control that makes every `Nothing` below discriminating: the same
        tree without the window answers `Nothing`, so a `Nothing` from a fixture
        that has one is the rule and not the fixture."""
        self.assertEqual(
            self.repl.rendered(
                ["reading |> Maybe.andThen dropboxWindowFromReading"],
                definitions=[reading_binding(
                    "reading", [ship_inventory(gauge=GAUGE_FULL)])])[0],
            "Nothing")


class TheWindowIsFoundByNameAndNeverByPositionTest(unittest.TestCase):
    """Every part read off the parts' own names, off a window drawn somewhere
    other than where it was captured.

    The 2026-09-09 capture put `DropboxWnd` at (760, 406), `inputInfo` at
    (782, 502) and `transferBtn` at (1055, 750). The fixtures here put them
    somewhere else entirely, so a rule that had taken any of those numbers finds
    nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parts(self, window):
        return self.repl.rendered(
            ["reading |> Maybe.andThen dropboxWindowFromReading"
             " |> Maybe.map (\\w -> ( w.dropTarget /= Nothing"
             " , w.transferButton /= Nothing, w.closeControl /= Nothing ))",
             "reading |> Maybe.andThen dropboxWindowFromReading"
             " |> Maybe.map .destinationText",
             "reading |> Maybe.andThen dropboxWindowFromReading"
             " |> Maybe.map .validRangeMeters"],
            definitions=[reading_binding("reading", [window])])

    def test_every_part_is_found_at_an_arbitrary_position(self):
        found, destination, valid_range = self.parts(
            dropbox_window(left=61, top=17))
        self.assertEqual(found, "Just (True,True,True)")
        self.assertEqual(destination, 'Just (Just "%s")' % DESTINATION_LABEL)
        self.assertEqual(valid_range, "Just (Just 10000)")

    def test_the_same_window_somewhere_else_reads_the_same(self):
        """Two positions, one answer -- which is what makes the case above a
        statement about the lookup rather than about one fixture."""
        self.assertEqual(self.parts(dropbox_window(left=61, top=17))[0],
                         self.parts(dropbox_window(left=901, top=433))[0])

    def test_a_window_missing_a_part_says_so_rather_than_defaulting(self):
        for kwargs, expected in (
                ({"with_drop_target": False}, "Just (False,True,True)"),
                ({"with_transfer_button": False}, "Just (True,False,True)"),
                ({"with_cancel": False}, "Just (True,True,False)")):
            with self.subTest(sorted(kwargs)):
                self.assertEqual(self.parts(dropbox_window(**kwargs))[0],
                                 expected)

    def test_the_valid_range_is_decoded_as_the_float_the_client_writes(self):
        """`validRange` reads `10000.0`, and a fractional one would answer
        `Nothing` under an `Int` decoder -- which prints as `unreadable` beside
        the number an operator is trying to check the bot's own gate against.

        **The integral value alone does not discriminate**, which a mutation
        found: JSON has one number type, so `Json.Decode.int` takes `10000.0`
        as readily as `float` does. The fractional case is what separates them
        and is asked for here, and the doc comment was corrected to say so.
        """
        self.assertEqual(self.parts(dropbox_window(valid_range=10000.0))[2],
                         "Just (Just 10000)")
        self.assertEqual(self.parts(dropbox_window(valid_range=7500.5))[2],
                         "Just (Just 7501)")
        self.assertEqual(self.parts(dropbox_window(valid_range=None))[2],
                         "Just Nothing")


class TheStagedCountIsTheScrollAndNotTheLabelTest(unittest.TestCase):
    """The trap the live drag turned up, in both directions.

    `numItemsLabel` counted **down** as staging succeeded -- `2 Items` with
    nothing staged, `1 Item` after one stack went in. A rule reading it as "how
    much is staged" therefore reports a successful drag as a failure and, worse,
    reports a *full hold with nothing staged* as two stacks ready to transfer.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def staged(self, window):
        return self.repl.rendered(
            ["reading |> Maybe.andThen dropboxWindowFromReading"
             " |> Maybe.map .stagedItems"],
            definitions=[reading_binding("reading", [window])])[0]

    def test_nothing_staged_reads_zero_however_the_label_counts(self):
        """The live reading exactly: the window is open, the hold holds two
        stacks, `numItemsLabel` reads `2 Items`, and **nothing is staged**."""
        self.assertEqual(self.staged(dropbox_window(item_count="2 Items")),
                         "Just 0")

    def test_one_stack_staged_reads_one_while_the_label_counts_down(self):
        """And the label reads `1 Item` on the same reading, which is the
        opposite direction. Whichever of the two a rule believes decides whether
        the drag looks like it worked."""
        self.assertEqual(
            self.staged(dropbox_window(
                item_count="1 Item", staged=[staged_stack("Fullerite-C84")])),
            "Just 1")

    def test_every_stack_staged_is_counted(self):
        self.assertEqual(
            self.staged(dropbox_window(
                item_count="0 Items",
                staged=[staged_stack("Fullerite-C84", 0),
                        staged_stack("Fullerite-C50", 1)])),
            "Just 2")

    def test_the_drop_hint_is_not_counted_as_a_staged_stack(self):
        """`inputScroll` carries its own caption, so a count over the scroll's
        descendants rather than over the stacks in it reads one with nothing
        staged."""
        self.assertEqual(self.staged(dropbox_window()), "Just 0")

    def test_nothing_decides_on_the_label(self):
        """It is carried so the next run can say what it counts, and read by the
        status line and by nothing else. A decision reading it is exactly the
        mistake the measurement above found."""
        declarations = top_level_declarations(bot_source())
        readers = [name for name, text in declarations.items()
                   if "itemCountLabelText" in collapsed(text)
                   and name not in ("DropboxWindow", "dropboxWindowFromNode")]
        self.assertEqual(sorted(readers), ["describeDeposit"], readers)


class TheTransferButtonStatesWhetherItWillDoAnythingTest(unittest.TestCase):
    """Disabled it carries two texts and enabled it carries one, measured live.

    That is the client's own enabled state rather than an inference, and it is
    the half of the commit gate that does not depend on this bot recognising
    what a staged stack renders as.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def ready(self, **kwargs):
        return self.repl.rendered(
            ["reading |> Maybe.andThen dropboxWindowFromReading"
             " |> Maybe.map .transferReadsReady"],
            definitions=[reading_binding(
                "reading", [dropbox_window(**kwargs)])])[0]

    def test_the_disabled_button_carries_both_texts_and_reads_not_ready(self):
        self.assertEqual(self.ready(transfer_texts=TRANSFER_DISABLED),
                         "Just False")

    def test_the_enabled_button_carries_one_text_and_reads_ready(self):
        self.assertEqual(self.ready(transfer_texts=TRANSFER_ENABLED),
                         "Just True")

    def test_a_window_with_no_transfer_button_is_never_ready(self):
        self.assertEqual(self.ready(with_transfer_button=False), "Just False")

    def test_the_order_of_the_texts_does_not_decide_it(self):
        """The capture recorded `['Nothing to transfer', 'Transfer']`, and a
        rule keyed on which text comes first would answer differently for a
        client that draws them the other way round. The marker is what decides,
        wherever it sits."""
        self.assertEqual(
            self.ready(transfer_texts=list(reversed(TRANSFER_DISABLED))),
            "Just False")


class TheWindowNamesWhereItIsTransferringToTest(unittest.TestCase):
    """`transferToLabel`, checked against the row the panel is showing.

    Matched against the overview row's own name rather than against
    `home-structure-name`, since that setting may end in `*` and mean a prefix
    while the question here is whether the window and the panel are talking
    about the same object.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def names(self, structure, destination):
        return self.repl.rendered(
            ["reading |> Maybe.andThen dropboxWindowFromReading"
             " |> Maybe.map (dropboxNamesTheStructure %s)"
             % json.dumps(structure)],
            definitions=[reading_binding(
                "reading", [dropbox_window(destination=destination)])])[0]

    def test_the_client_s_own_label_names_the_structure_through_the_colon(self):
        """`Structure to transfer to:<structure>` glues the name to the word
        before it, so the colon has to be read as a separator -- a whole-word
        match over the raw text answers `False` for the label the client
        actually writes."""
        self.assertEqual(
            self.names(FICTIONAL_STRUCTURE, DESTINATION_LABEL), "Just True")

    def test_a_label_naming_somewhere_else_declines(self):
        self.assertEqual(
            self.names(FICTIONAL_STRUCTURE,
                       "Structure to transfer to:%s" % ANOTHER_STRUCTURE),
            "Just False")

    def test_a_label_this_bot_cannot_read_declines_rather_than_assuming(self):
        """Which is the direction that stops a transfer nothing corroborated,
        and which the deposit answers by saying so and waiting."""
        self.assertEqual(self.names(FICTIONAL_STRUCTURE, None), "Just False")

    def test_a_name_that_is_only_a_substring_of_the_label_declines(self):
        """Whole words rather than a substring, which is the trap this repo has
        already paid for once -- a rogue drone called a `Wrecker` contains
        `wreck`. Two structures an operator could plausibly have, one of whose
        names sits inside the other's first word: a substring rule reads the
        window as naming the panel's structure and drags a hold into it.
        """
        self.assertEqual(
            self.names("Camp", "Structure to transfer to:Campaign HQ"),
            "Just False")
        # And the whole word, in the same label, is matched -- so the case above
        # is about the word boundary rather than about the name being short.
        self.assertEqual(
            self.names("Camp", "Structure to transfer to:Camp"), "Just True")

    def test_a_near_miss_between_two_real_names_declines(self):
        """`Fictional II` against a label naming `Fictional IX`, one character
        apart, which both a substring and a whole-word rule decline. Kept as the
        control that the case above is not the only thing being asked."""
        self.assertEqual(
            self.names("Fictional II",
                       "Structure to transfer to:%s" % FICTIONAL_STRUCTURE),
            "Just False")


class TheSequenceIsTheOneThatWasDrivenByHandTest(unittest.TestCase):
    """`depositStep`, over the in-space branch, in the order the live sequence
    ran: select, press Access Dropbox, drag each stack, press Transfer.

    Asked of the record rather than of a reading, because several of these are
    combinations no single fixture can be in at once -- a window open with the
    hold drained and stacks staged, for one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, **kwargs):
        return self.repl.rendered(["depositStep %s" % situation(**kwargs)])[0]

    def test_the_panel_is_shown_the_structure_before_anything_is_pressed(self):
        self.assertEqual(
            self.step(panel_shows=False, access_dropbox_offered=True,
                      within_dropbox_range=True),
            "SelectTheHomeStructure")

    def test_the_dropbox_is_opened_where_it_is_offered_and_in_range(self):
        self.assertEqual(
            self.step(access_dropbox_offered=True, within_dropbox_range=True),
            "PressTheAccessDropboxButton")

    def test_each_stack_is_dragged_while_the_hold_still_shows_one(self):
        self.assertEqual(
            self.step(dropbox_open=True, items=2), "DragTheHoldIntoTheDropbox")
        # The reading the live sequence spent most of: one stack staged, the
        # button already enabled by it, and one stack still in the hold. The
        # drag has to outrank the transfer here or the run ends on the first
        # confirmation with the rest of the hold still aboard.
        self.assertEqual(
            self.step(dropbox_open=True, items=1, dropbox_staged=1,
                      dropbox_transfer_ready=True),
            "DragTheHoldIntoTheDropbox")

    def test_the_transfer_is_committed_once_the_hold_is_drained(self):
        """Drag-all-then-transfer rather than a transfer per stack: the first
        confirmation ends the run, so a transfer per stack would end it with
        stacks still in the hold."""
        self.assertEqual(
            self.step(dropbox_open=True, items=0, dropbox_staged=2,
                      dropbox_transfer_ready=True),
            "PressTheTransferButton")

    def test_the_hold_is_selected_before_a_stack_is_looked_for(self):
        self.assertEqual(
            self.step(dropbox_open=True, hold_selected=False, items=2),
            "SelectTheHold")

    def test_a_transfer_in_flight_is_waited_through_above_all_of_it(self):
        self.assertEqual(
            self.step(dropbox_open=True, hold="HoldTransferIsInFlight",
                      items=2),
            "WaitThroughTheTransfer")

    def test_a_warping_ship_is_left_alone_above_the_window(self):
        self.assertEqual(self.step(dropbox_open=True, warping=True, items=2),
                         "WaitForTheWarpToLand")


class NothingIsCommittedWithoutBothReadingsTest(unittest.TestCase):
    """The commit gate, which is #476's "prefer the window's own evidence".

    Two independent readings of the same fact -- what `inputScroll` is holding
    and what the client says about its own button -- and both have to agree.
    Either one alone is a transfer pressed on a window that may have nothing in
    it, which is what #464 had to wait for a game-log line to find out about.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, **kwargs):
        return self.repl.rendered(["depositStep %s" % situation(**kwargs)])[0]

    def test_a_ready_button_with_nothing_staged_does_not_commit(self):
        self.assertEqual(
            self.step(dropbox_open=True, items=0, dropbox_staged=0,
                      dropbox_transfer_ready=True),
            "TheDropboxHasNothingStagedToTransfer")

    def test_a_staged_stack_with_the_button_unready_does_not_commit(self):
        self.assertEqual(
            self.step(dropbox_open=True, items=0, dropbox_staged=2,
                      dropbox_transfer_ready=False),
            "TheDropboxHasNothingStagedToTransfer")

    def test_both_together_commit_and_that_is_the_only_way_to(self):
        self.assertEqual(
            self.step(dropbox_open=True, items=0, dropbox_staged=1,
                      dropbox_transfer_ready=True),
            "PressTheTransferButton")

    def test_a_window_naming_somewhere_else_stages_nothing_at_all(self):
        """Asked before the hold is even looked at, so a mismatch cannot reach a
        drag either -- the ship keeps its cargo rather than putting it into a
        window nothing corroborated."""
        self.assertEqual(
            self.step(dropbox_open=True, items=2,
                      dropbox_names_structure=False),
            "TheDropboxWindowDoesNotNameTheSelectedStructure")

    def test_a_window_this_bot_cannot_read_stages_nothing_either(self):
        self.assertEqual(
            self.step(dropbox_open=True, items=2, dropbox_usable=False),
            "TheDropboxWindowIsNotUsable")

    def test_the_facts_the_rule_decides_on_come_off_the_window_itself(self):
        """Read out of `depositSituationFromContext` rather than executed,
        because it takes a whole `BotDecisionContext` (#106) and nothing can run
        it -- which is exactly why it is read rather than left unasserted.

        Each of these is a way the rule above could be handed a fact that is
        true of nothing: a window called usable because it exists, a staged
        count defaulted rather than read, a destination taken as agreed. The
        record is plain facts precisely so the rule can be executed, and this is
        the seam where those facts are made.
        """
        body = collapsed(top_level_declarations(bot_source())[
            "depositSituationFromContext"])
        for clause in (
                ", dropboxWindowIsOpen = dropbox /= Nothing",
                ", dropboxNamesTheSelectedStructure ="
                " Maybe.map2 dropboxNamesTheStructure"
                " (homeStructureRow |> Maybe.andThen .objectName) dropbox"
                " |> Maybe.withDefault False",
                ", dropboxIsUsable = dropbox |> Maybe.map"
                " (\\found -> (found.dropTarget /= Nothing)"
                " && (found.transferButton /= Nothing))"
                " |> Maybe.withDefault False",
                ", dropboxStagedItems ="
                " dropbox |> Maybe.map .stagedItems |> Maybe.withDefault 0",
                ", dropboxTransferReadsReady = dropbox |> Maybe.map"
                " .transferReadsReady |> Maybe.withDefault False"):
            with self.subTest(clause.split("=")[0].strip()):
                self.assertIn(clause, body)


class TheDockedDepositIsStillTheFallbackTest(unittest.TestCase):
    """#476's own constraint: a structure offering no dropbox, or a reading
    where the window cannot be found, must still deposit rather than stall.

    Three separate falls, and each is a different thing being absent.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, **kwargs):
        return self.repl.rendered(["depositStep %s" % situation(**kwargs)])[0]

    def test_a_structure_offering_no_dropbox_docks(self):
        self.assertEqual(
            self.step(access_dropbox_offered=False, dock_offered=True),
            "PressTheDockButton")

    def test_a_ship_out_of_dropbox_range_docks_rather_than_opening_it(self):
        """The button was pressed successfully at roughly 90 km in one recorded
        attempt, so the panel offering it is not evidence a transfer would land.
        The gate is this bot's own and is deliberately tighter."""
        self.assertEqual(
            self.step(access_dropbox_offered=True, within_dropbox_range=False,
                      dock_offered=True),
            "PressTheDockButton")

    def test_a_ship_out_of_both_ranges_warps_exactly_as_it_did(self):
        self.assertEqual(
            self.step(access_dropbox_offered=True, within_dropbox_range=False,
                      dock_offered=False),
            "WarpToTheHomeStructure")

    def test_the_docked_arm_is_untouched_by_any_of_this(self):
        """A docked reading never asks about a dropbox at all, so #464's
        sequence answers exactly what it answered before."""
        for kwargs, expected in (
                ({}, "DragTheHoldIntoTheStructureHangar"),
                ({"confirmed": True}, "Undock"),
                ({"hangar_in_inventory": False},
                 "NoStructureHangarInTheInventory"),
                ({"ok_on_screen": True}, "ConfirmWhateverDialogIsOnScreen")):
            with self.subTest(sorted(kwargs)):
                self.assertEqual(
                    self.step(docked=True, dropbox_open=True,
                              access_dropbox_offered=True,
                              within_dropbox_range=True, **kwargs),
                    expected)

    def test_the_range_gate_is_read_from_the_structure_s_own_distance(self):
        """And an unreadable distance is not within range, so a row that is not
        rendered or that reports AU falls back to docking rather than opening a
        window the bot cannot place."""
        body = collapsed(top_level_declarations(bot_source())[
            "depositSituationFromContext"])
        self.assertIn(
            "structureIsWithinDropboxRange ="
            " rangeToTheHomeStructureInMeters settings.homeStructureName"
            " readingFromGameClient |> Maybe.map"
            " (\\meters -> meters <= dropboxTransferRangeMeters)"
            " |> Maybe.withDefault False", body)


class TheRunWaitsForTheWindowItOpenedTest(unittest.TestCase):
    """A deposit does not end while the transfer window is still on screen.

    The reading that would otherwise end the run -- the confirmation, or the
    hold reading empty in space -- is the same reading the window is finished
    with, so ending there leaves a 400x400 window over a client this bot clicks
    at screen positions on.

    **And a window with no close control ends the run exactly as before**, which
    is what stops a window shape this bot does not recognise from stranding a
    deposit.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def after(self, hold, confirmation, dropbox_open,
              before="Just { readings = 9, confirmation = Nothing, drags = 2 }"):
        return self.repl.rendered([
            "depositRunAfterReading"
            " { before = %s"
            " , holdFill = %s, docked = False, confirmationNow = %s"
            " , dragDispatched = False, dropboxWindowIsOpen = %s }" % (
                before, hold,
                "Nothing" if confirmation is None
                else "(Just %s)" % json.dumps(confirmation),
                "True" if dropbox_open else "False")])[0]

    def test_a_full_hold_starts_a_run_whether_or_not_a_window_stands(self):
        """The clause is about *ending* a run and must not reach the start of
        one: a session whose last deposit left a window open would otherwise
        never notice the next full hold."""
        for dropbox_open in (True, False):
            with self.subTest(dropbox_open):
                self.assertEqual(
                    self.after("HoldIsFull", None, dropbox_open,
                               before="Nothing"),
                    "Just { confirmation = Nothing, drags = 0, readings = 1 }")

    def test_the_confirmation_does_not_end_it_while_the_window_stands(self):
        self.assertEqual(
            self.after("HoldHasRoom", IN_SPACE_CONFIRMATION, True),
            'Just { confirmation = Just "%s", drags = 2, readings = 10 }'
            % IN_SPACE_CONFIRMATION)

    def test_it_ends_on_the_reading_the_window_has_gone(self):
        self.assertEqual(
            self.after("HoldHasRoom", IN_SPACE_CONFIRMATION, False), "Nothing")

    def test_an_empty_hold_in_space_does_not_end_it_either_while_it_stands(self):
        self.assertEqual(self.after("HoldHasRoom", None, True),
                         "Just { confirmation = Nothing, drags = 2"
                         ", readings = 10 }")
        self.assertEqual(self.after("HoldHasRoom", None, False), "Nothing")

    def test_a_full_hold_is_unaffected_by_the_window_either_way(self):
        for dropbox_open in (True, False):
            with self.subTest(dropbox_open):
                self.assertEqual(
                    self.after("HoldIsFull", None, dropbox_open),
                    "Just { confirmation = Nothing, drags = 2"
                    ", readings = 10 }")

    def test_the_input_is_a_window_this_bot_could_close_and_not_merely_one(self):
        """The wiring that makes an unclosable window end the run: the memory
        update asks for the close control rather than for the window."""
        body = collapsed(top_level_declarations(bot_source())[
            "updateMemoryForNewReadingFromGame"])
        self.assertIn(
            "dropboxWindowIsOpen = dropboxWindowFromReading"
            " context.readingFromGameClient |> Maybe.andThen .closeControl"
            " |> (/=) Nothing", body)

    def test_the_finished_deposit_closes_the_window(self):
        answers = self.repl.rendered([
            "depositStep %s" % situation(dropbox_open=True, confirmed=True,
                                         hold="HoldHasRoom", items=0),
            "depositStep %s" % situation(dropbox_open=True, confirmed=False,
                                         hold="HoldHasRoom", items=0),
        ])
        self.assertEqual(answers, ["CloseTheDropboxWindow",
                                   "CloseTheDropboxWindow"])

    def test_a_half_staged_window_is_not_closed_on_an_emptied_hold(self):
        """The hazard the close's second clause exists for, and it rests on
        something **unmeasured**: `numItemsLabel` counts down as stacks are
        staged, which is consistent with a stack leaving the hold the moment it
        goes in -- and whether the capacity gauge follows it nobody has watched.

        If it does, a half-staged window is a reading whose hold says
        `HoldHasRoom`, and closing there cancels a transfer with the ship's
        cargo inside it. The close waits for `inputScroll` to be empty instead,
        which is true after the transfer either way.
        """
        self.assertEqual(
            self.repl.rendered([
                "depositStep %s" % situation(
                    dropbox_open=True, hold="HoldHasRoom", items=0,
                    dropbox_staged=2, dropbox_transfer_ready=True)])[0],
            "PressTheTransferButton")
        # And with the hold still showing a stack, the drag goes on.
        self.assertEqual(
            self.repl.rendered([
                "depositStep %s" % situation(
                    dropbox_open=True, hold="HoldHasRoom", items=1,
                    dropbox_staged=1, dropbox_transfer_ready=True)])[0],
            "DragTheHoldIntoTheDropbox")


class TheRetreatStillOutranksTheDepositTest(unittest.TestCase):
    """#462/#463's ordering, re-asserted because #476 makes it matter more.

    A stationary ship with a full hold beside a structure, dragging stacks into
    a window, is exactly the case the retreat exists for -- and inverting the
    ordering compiles.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()
        cls.declarations = top_level_declarations(bot_source())

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def ordering(self):
        return " ".join([
            collapsed(self.declarations["watchLeaveDepositOrHarvest"]),
            collapsed(self.declarations["leaveDepositOrHarvest"]),
        ])

    def test_the_leaving_is_still_asked_before_the_deposit(self):
        body = self.ordering()
        self.assertLess(body.index("actOnTheEvasionStep"),
                        body.index("actOnTheDepositStep"), body)

    def test_both_are_still_above_the_docked_or_in_space_split(self):
        body = self.ordering()
        for above in ("actOnTheEvasionStep", "actOnTheDepositStep"):
            with self.subTest(above):
                self.assertLess(body.index(above),
                                body.index("branchDependingOnDockedOrInSpace"),
                                body)

    def test_the_transfer_would_have_gone_on_upon_that_same_reading(self):
        """What makes the ordering above load-bearing rather than decorative:
        on a grid that has stopped reading clean, the evasion answers a leave
        and the deposit answers a drag, so which one the bot takes is decided by
        placement and by nothing else."""
        leaving, depositing = self.repl.rendered([
            "evasionStep %s" % evasion_situation(docked=False, clean=False),
            "depositStep %s" % situation(dropbox_open=True, items=2),
        ])
        self.assertEqual(leaving, "ActivateTheCloak 2")
        self.assertEqual(depositing, "DragTheHoldIntoTheDropbox")

    def test_the_dropbox_reaches_no_decision_above_the_evasion(self):
        """The whole of this change lives under `actOnTheDepositStep`, so
        nothing it added can be asked before the retreat has had its say."""
        for name in ("dropboxWindowFromReading", "accessDropboxButtonInReading",
                     "dropboxNamesTheStructure"):
            with self.subTest(name):
                self.assertNotIn(name, self.ordering())


class TheParserIsStillNotTouchedTest(unittest.TestCase):
    """#476 says a parser change here would be an eight-copy concern (#467) and
    wants saying out loud. None was needed and none was made."""

    def test_the_window_is_reached_through_the_raw_tree(self):
        body = collapsed(top_level_declarations(bot_source())[
            "dropboxWindowFromReading"])
        self.assertIn("readingFromGameClient.uiTree"
                      " |> EveOnline.ParseUserInterface"
                      ".listDescendantsWithDisplayRegion", body)

    def test_the_vendored_parser_still_matches_wingman_byte_for_byte(self):
        import os
        from test_gas_huffer_scaffold import GAS_HUFFER_DIR
        apps = os.path.dirname(GAS_HUFFER_DIR)

        def parser(app):
            with open(os.path.join(apps, app, "EveOnline",
                                   "ParseUserInterface.elm"),
                      encoding="utf-8") as handle:
                return handle.read()

        self.assertEqual(parser("eve-online-gas-huffer"),
                         parser("eve-online-wingman"))

    def test_the_node_names_are_constants_rather_than_literals_at_the_site(self):
        """So the status line and the rules quote what the lookup matched, and a
        client that renames one is one edit rather than a hunt."""
        declarations = top_level_declarations(bot_source())
        lookups = " ".join(
            collapsed(declarations[name])
            for name in ("dropboxWindowFromReading", "dropboxWindowFromNode",
                         "dropboxCloseControl", "dropboxNamesTheStructure",
                         "accessDropboxButtonInReading", "depositStep",
                         "actOnTheDepositStep", "describeDeposit"))
        for name, expected in (
                ("dropboxWindowTypeName", "DropboxWnd"),
                ("dropboxDropTargetTypeName", "TransferInputContainer"),
                ("dropboxStagedItemsContainerName", "inputScroll"),
                ("dropboxTransferButtonName", "transferBtn"),
                ("dropboxDestinationLabelName", "transferToLabel"),
                ("dropboxItemCountLabelName", "numItemsLabel"),
                ("dropboxValidRangeKey", "validRange"),
                ("selectedItemAccessDropboxElementId",
                 "selectedItemAccessDropbox"),
                ("dropboxNothingToTransferMarker", "Nothing to transfer")):
            with self.subTest(name):
                self.assertIn('"%s"' % expected,
                              collapsed(declarations[name]))
                # And the string occurs *only* there: a lookup carrying its own
                # copy is a rename that lands in one of two places.
                self.assertNotIn('"%s"' % expected, lookups)


class TheClientConfirmsBothWaysItWritesTheSentenceTest(unittest.TestCase):
    """The live in-space transfer wrote a sentence #464's markers did not match.

    #456 recorded `N item(s) was moved to your hangar in <system> -
    <structure>`; 2026-09-10 produced `2 items were moved to your hangar in
    <structure>` -- plural verb, no system. `item(s) was moved` matches neither
    the second nor anything like it, so the markers are widened to what both
    carry and the near miss is asked about beside them.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def matches(self, text):
        """Asked through `depositConfirmedInGameLog` over a real parsed reading
        rather than of the markers directly, so what is executed is the whole
        path the run's own verdict takes -- the channel filter included."""
        return self.repl.rendered(
            ["reading |> Maybe.andThen depositConfirmedInGameLog"
             " |> (/=) Nothing"],
            definitions=[reading_binding(
                "reading", [game_log([("notify", text)])])])[0]

    def test_both_wordings_the_client_has_written_are_matched(self):
        for text in (
                "8 item(s) was moved to your hangar in J000000 - %s"
                % FICTIONAL_STRUCTURE,
                IN_SPACE_CONFIRMATION):
            with self.subTest(text):
                self.assertEqual(self.matches(text), "True")

    def test_a_sentence_about_a_hangar_carrying_no_item_still_declines(self):
        self.assertEqual(
            self.matches("Your ship was moved to your hangar in J000000 - %s"
                         % FICTIONAL_STRUCTURE),
            "False")

    def test_an_unrelated_notify_line_still_declines(self):
        self.assertEqual(
            self.matches(
                "Gas Cloud Harvester I deactivates without transfering ore to"
                " your cargo hold because your ship has strayed to a distance"
                " of 1628.94 m, beyond its mining range of 1500.00 m."),
            "False")


class TheStatusLineSaysWhatTheWindowIsDoingTest(unittest.TestCase):
    """What an operator watching the first run reads, since none of this has
    ever run and the clause is how the premises get checked."""

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def clause(self, window=None, offered=False, range_meters=None):
        """The clause, with the window it reports on **parsed off a real tree**
        rather than written out as a record -- so what the status line prints is
        what the lookup would have handed it."""
        definitions = []
        if window is None:
            dropbox = "Nothing"
        else:
            definitions.append(reading_binding("reading", [window]))
            dropbox = "(reading |> Maybe.andThen dropboxWindowFromReading)"
        return self.repl.strings([
            "describeDeposit { holdFill = HoldIsFull, deposit = Nothing"
            ", dockingRunIn = Nothing, homeStructureName = %s"
            ", depositChainHop ="
            " { hopsMade = 0, lastSolarSystemName = Nothing }"
            ", dropbox = %s, accessDropboxIsOffered = %s"
            ", rangeToTheStructureMeters = %s }" % (
                "(Just %s)" % json.dumps(FICTIONAL_STRUCTURE), dropbox,
                "True" if offered else "False",
                "Nothing" if range_meters is None
                else "(Just %d)" % range_meters)],
            definitions=definitions)[0]

    def test_a_closed_window_says_whether_the_panel_offers_one_and_how_far(self):
        printed = self.clause(offered=True, range_meters=2339)
        self.assertIn("no transfer window open", printed)
        self.assertIn("selectedItemAccessDropbox", printed)
        self.assertIn("2339 m", printed)
        self.assertIn("10000 m this bot will open it at", printed)

    def test_an_unreadable_range_says_so_rather_than_printing_a_number(self):
        self.assertIn("at a range this reading cannot say",
                      self.clause(offered=True))

    def test_an_open_window_carries_every_reading_the_commit_rests_on(self):
        printed = self.clause(window=dropbox_window(
            item_count="1 Item", transfer_texts=TRANSFER_ENABLED,
            staged=[staged_stack("Fullerite-C84", 0),
                    staged_stack("Fullerite-C50", 1)]))
        self.assertIn("OPEN", printed)
        self.assertIn(DESTINATION_LABEL, printed)
        self.assertIn("2 stack(s) staged", printed)
        self.assertIn("READY", printed)
        self.assertIn("closable", printed)
        self.assertIn("validRange 10000 m", printed)
        # And the label that is not a staged count says what it is, so nobody
        # reading the log concludes one stack is staged from `1 Item` while the
        # clause beside it says two.
        self.assertIn("1 Item", printed)
        self.assertIn("counts the hold rather than what is staged", printed)

    def test_a_window_nothing_can_shut_says_so(self):
        """Which is the one an operator has to act on: it ends the run rather
        than holding it, so the deposit finishes and the window stays."""
        self.assertIn("NO CLOSE CONTROL",
                      self.clause(window=dropbox_window(with_cancel=False)))

    def test_a_button_that_is_not_ready_quotes_what_it_reads(self):
        self.assertIn("reading 'Nothing to transfer'",
                      self.clause(window=dropbox_window()))


class TheMutationsThisFileCatches(unittest.TestCase):
    """Confirmed by mutation. Each of these was applied to `Bot.elm`, the suite
    was run, and the named case failed; the list is here so a later reader can
    re-run them.

    The three #476 names by hand are 1, 2 and 3.

    1.  **the docking fallback removed** -- `depositStep` answering
        `PressTheAccessDropboxButton` wherever the panel offers it, with the
        `dockButtonIsOffered` arm below it deleted --
        `TheDockedDepositIsStillTheFallbackTest`, three cases.
    1b. the softer half of the same thing: the range clause dropped, so the
        window is opened wherever the panel offers it -- 90 km included --
        `test_a_ship_out_of_dropbox_range_docks_rather_than_opening_it`.
    2.  **the retreat ordering inverted** -- `leaveDepositOrHarvest` asking
        `actOnTheDepositStep` before `actOnTheEvasionStep` --
        `TheRetreatStillOutranksTheDepositTest.test_the_leaving_is_still_asked_
        before_the_deposit`, and #464's own copy of the same relation next
        door. `test_the_transfer_would_have_gone_on_upon_that_same_reading` is
        the control that makes it an ordering rather than a coincidence.
    3.  **the transfer committed without checking the staged count** --
        `PressTheTransferButton` gated on `dropboxTransferReadsReady` alone --
        `NothingIsCommittedWithoutBothReadingsTest.test_a_ready_button_with_
        nothing_staged_does_not_commit`.
    3b. the mirror: gated on the staged count alone, so a window whose button
        reads `Nothing to transfer` is pressed anyway -- `test_a_staged_stack_
        with_the_button_unready_does_not_commit`.
    4.  `stagedItems` counting every descendant of `inputScroll` rather than the
        stacks in it, so the drop hint reads as one staged stack and a window
        with nothing in it commits -- four cases in
        `TheStagedCountIsTheScrollAndNotTheLabelTest` plus the status clause.
    5.  `transferReadsReady` answering `True` for any button that is there,
        which is what pressing hopefully looks like -- `TheTransferButton
        StatesWhetherItWillDoAnythingTest`, two cases, plus the status clause
        that quotes what the button reads.
    6.  the destination check dropped from the rule, so a window naming another
        structure is dragged into -- `test_a_window_naming_somewhere_else_
        stages_nothing_at_all`.
    6b. `dropboxNamesTheStructure` weakened to `String.contains`, which is this
        repo's `Wrecker`/`wreck` trap -- `test_a_name_that_is_only_a_substring_
        of_the_label_declines`. **This one survived the first pass**: the case
        was asking about `Fictional II` against a label naming `Fictional IX`,
        which a substring rule declines too, so it discriminated nothing. It
        asks about a name sitting inside another's first word now.
    6c. the colon left unreplaced, so the client's own label matches nothing --
        `test_the_client_s_own_label_names_the_structure_through_the_colon`.
    7.  `dropboxIsUsable` answering `True` for any window that exists, so a
        window with no transfer button is staged into -- `test_the_facts_the_
        rule_decides_on_come_off_the_window_itself`. **This one survived the
        first pass too**, and the hole was structural: every other case here
        hands `depositStep` a record, so none of them can see the seam where
        the record is *made*. `depositSituationFromContext` takes a whole
        `BotDecisionContext` and cannot be executed (#106), so that seam is
        read out of the source, which is what the case now does.
    8.  the run's window clause dropped from `depositRunAfterReading`, so the
        confirmation ends the run with the window still on screen --
        `TheRunWaitsForTheWindowItOpenedTest`, two cases.
    8b. the same clause fed the *window* rather than its close control, so a
        window nothing can shut strands the deposit until the bound --
        `test_the_input_is_a_window_this_bot_could_close_and_not_merely_one`.
    8c. the clause conjoined onto the arm that *starts* a run, so a session
        whose last deposit left a window open never notices the next full hold
        -- `test_a_full_hold_starts_a_run_whether_or_not_a_window_stands`.
        **Survived the first pass**: every case was folding from a run already
        under way, so none of them reached the starting arm at all.
    10. `validRangeMeters` read through `getIntPropertyFromDictEntries` --
        `test_the_valid_range_is_decoded_as_the_float_the_client_writes`.
        **Survived the first pass, and it was the doc comment that was wrong
        rather than the case.** That comment claimed an `Int` decoder would
        answer `Nothing` for `10000.0`; JSON has one number type, so it does
        not. The comment is corrected and the case asks about a fractional
        range, which is what actually separates the two decoders.
    17. the close no longer waiting for the staging to be finished, so a
        half-staged window is shut on a hold that reads `HoldHasRoom` --
        `test_a_half_staged_window_is_not_closed_on_an_emptied_hold`. That
        clause guards something **unmeasured**: whether the capacity gauge
        drains as stacks are staged, which `numItemsLabel` counting down makes
        plausible and nobody has watched.
    12. a decision reading `itemCountLabelText` -- the label that counts the
        hold rather than what is staged -- `test_nothing_decides_on_the_label`.
    13. the dropbox lookup hoisted into `leaveDepositOrHarvest` above the
        evasion -- `test_the_dropbox_reaches_no_decision_above_the_evasion`.
    14. the drag arm ordered after the transfer arm, so the first stack is
        committed alone and the run ends with the rest still in the hold --
        `test_each_stack_is_dragged_while_the_hold_still_shows_one`.
        **Survived the first pass**: the case was asking about a reading whose
        button was not ready, where the ordering cannot matter. It asks about
        the reading the live sequence actually spent -- one stack staged, the
        button already enabled by it, one stack still in the hold.
    15. the window branch placed above `shipIsWarping`, so a ship in warp is
        dragged out of -- `test_a_warping_ship_is_left_alone_above_the_window`.
    16. a node type name inlined at its lookup rather than named --
        `test_the_node_names_are_constants_rather_than_literals_at_the_site`.
        **Survived the first pass**: the case asserted the constant carried the
        right literal and never that the lookup used the constant. It refuses
        the literal anywhere else now.
    11. `depositConfirmationMarkers` reverted to #464's `item(s) was moved`, so
        the sentence the live transfer produced matches nothing --
        `TheClientConfirmsBothWaysItWritesTheSentenceTest.test_both_wordings_
        the_client_has_written_are_matched`.
    11b. widened to `moved to your hangar` alone, which takes the sentence about
        a ship -- `test_a_sentence_about_a_hangar_carrying_no_item_still_
        declines`, and #464's own `test_one_marker_is_not_enough` beside it.
    """

    def test_the_list_above_is_the_documentation(self):
        self.assertTrue(self.__doc__)


if __name__ == "__main__":
    unittest.main()
