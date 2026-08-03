"""Tests for the module-state dict entries #35 found sitting unread on the button.

CLAUDE.md said the state was unavailable on this build, and half of that was
measured: walking a top-row module button's whole subtree finds one sprite,
`underlay`, so the parser's `hilite` and `busy` lookups cannot return anything
but `False`. The other half was an inference, and it was wrong. The button's own
`dictEntriesOfInterest` carries twelve entries -- `ramp_active`,
`isInActiveState`, `isDeactivating`, `effect_activating`, `online`, `blinking`,
`grey`, `quantity`, `autoreload`, `autorepeat`, `isMaster`,
`waitingForActiveTarget` -- and nothing had ever read one.

**What these cases protect is that the fields are exposed and nothing acts on
them.** A 240s read-only sample of run 9 has since measured most of what they
mean -- `ramp_active` oscillated fourteen times while the gun stayed switched
on, so it is a duty cycle rather than an on/off state -- but that is one window
on one fit, and the entry #34 hung on has no observations at all:
`isDeactivating` was never once `True`, because nothing switched a module off
while the sampler ran. #12 and #34 are both a decision built on a field's assumed
meaning. So `isActive`, `isBusy` and `isHiliteVisible` keep the meanings they
had, the new fields reach the status line and stop there, and
`test_nothing_but_the_status_line_reads_them` is what keeps that true as the
file changes around it.

The parser is vendored six times and the policy is all six identically, so the
block is compared byte for byte the way `test_game_log_channel.py` compares the
game-log block.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
APPS_DIR = os.path.join(REPO_DIR, "implement", "applications", "eve-online")
MISSION_RUNNER_BOT_ELM = os.path.join(
    APPS_DIR, "eve-online-mission-runner", "Bot.elm")

# The client's own keys, spelled the client's way. The parser's record fields
# carry the same names unchanged so that a value in a log line and a value in
# the UI tree are the same word and no translation table has to be right.
DICT_ENTRY_KEYS = [
    "ramp_active",
    "isInActiveState",
    "isDeactivating",
    "effect_activating",
    "online",
    "blinking",
    "grey",
    "quantity",
    "autoreload",
    "autorepeat",
    "isMaster",
    "waitingForActiveTarget",
]

# What the status line prints: the four the issue asks a live run to record
# across idle -> activated -> firing -> commanded off -> settled, plus
# `isInActiveState`, which the 240s sample showed is the switched-on flag and
# therefore the only thing that makes `ramp_active` readable -- `False` there
# means "between cycles" while the module is on and "not running" once it is
# off, and the switch-off leg is exactly where those two diverge.
KEYS_IN_THE_STATUS_LINE = [
    "ramp_active",
    "isInActiveState",
    "isDeactivating",
    "effect_activating",
    "waitingForActiveTarget",
]

TYPE_ALIAS_FIELD = "    , stateFromDictEntries : ShipUIModuleButtonState\n"
PARSE_CALL = (
    "    , stateFromDictEntries = parseShipUIModuleButtonState moduleButtonNode.uiNode\n")


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


class VendoredParserTest(unittest.TestCase):
    """`ParseUserInterface.elm` is vendored six times; the policy is all six.

    Same check #30 put on the game-log block. A change that lands in one copy
    and silently not the others is its own bug, and here it would be a quiet
    one: a bot whose copy lacks the fields logs `-` for every entry on every
    reading, which is indistinguishable from a client that does not carry them.
    That is the exact reading this issue exists to correct.
    """

    def setUp(self):
        self.sources = {}
        for app in sorted(os.listdir(APPS_DIR)):
            path = os.path.join(app, "EveOnline", "ParseUserInterface.elm")
            full = os.path.join(APPS_DIR, path)
            if os.path.isfile(full):
                with open(full, encoding="utf-8") as handle:
                    self.sources[full] = handle.read()
        if not self.sources:
            self.skipTest(f"no vendored parsers under {APPS_DIR}")

    def block(self, source):
        start = source.index("{-| What a module button says about **itself**")
        end = source.index("jsonDecodeIntFromIntOrBool =")
        return source[start:source.index("\n\n\n", end)]

    def test_every_copy_has_it(self):
        self.assertEqual(len(self.sources), 6, sorted(self.sources))
        for path, source in self.sources.items():
            self.assertIn(TYPE_ALIAS_FIELD, source, path)
            self.assertIn(PARSE_CALL, source, path)

    def test_every_copy_has_the_same_one(self):
        blocks = {path: self.block(source) for path, source in self.sources.items()}
        reference = blocks[sorted(blocks)[0]]
        for path, block in blocks.items():
            self.assertEqual(block, reference, path)

    def test_every_dict_entry_the_button_carries_is_read(self):
        for path, source in self.sources.items():
            block = self.block(source)
            for key in DICT_ENTRY_KEYS:
                self.assertIn(f'"{key}"', block, f"{path}: {key} not read")

    def test_it_adds_no_tree_walk(self):
        # The parser is syscall-bound and a full read is thousands of nodes, so
        # the cost of this has to stay twelve dictionary lookups on a node the
        # caller already holds. Taking the bare `UITreeNode` is what makes that
        # structural rather than a promise: `listDescendantsWithDisplayRegion`
        # cannot be applied to it, which is precisely what the sprite lookups
        # this replaces each do once per module per reading.
        for path, source in self.sources.items():
            block = self.block(source)
            self.assertNotIn("listDescendants", block, path)
            self.assertIn(
                "parseShipUIModuleButtonState : EveOnline.MemoryReading.UITreeNode"
                " -> ShipUIModuleButtonState", block, path)

    def test_an_entry_that_does_not_decode_is_nothing(self):
        # Never a guessed `False`. Absent and false are different answers about
        # a module, and only one of them is safe to act on -- which is the same
        # distinction `Nothing` vs `Just []` carries for the game log channel.
        for path, source in self.sources.items():
            block = self.block(source)
            self.assertIn("Result.toMaybe", block, path)
            self.assertNotIn("Maybe.withDefault", block, path)

    def test_every_field_can_say_absent(self):
        # Measured, not hypothetical: no module carried `ramp_active` for the
        # first ~60s of the 240s sample -- missing, not `False` -- and
        # `waitingForActiveTarget` appeared on all four modules at once at
        # 141.3s. A field typed `Bool` would have recorded both as `False` and
        # made "off" and "has never run" the same fact.
        for path, source in self.sources.items():
            alias_start = self.block(source).index("type alias ShipUIModuleButtonState =")
            alias = self.block(source)[alias_start:]
            alias = alias[:alias.index("\n    }")]
            fields = [line for line in alias.split("\n") if " : " in line]
            self.assertEqual(len(fields), len(DICT_ENTRY_KEYS), path)
            for field in fields:
                self.assertIn(" : Maybe ", field, f"{path}: {field.strip()}")

    def test_both_json_shapes_decode(self):
        # The sample shows booleans for `ramp_active` and its neighbours and
        # plain numbers for `waitingForActiveTarget` and the rest, but one
        # sample is not a guarantee about the build. A copy that accepted only
        # the observed shape would answer `Nothing` for a client sending the
        # other one, which reads exactly like "this state is not available"
        # again.
        for path, source in self.sources.items():
            block = self.block(source)
            for decoder in ("jsonDecodeBoolFromBoolOrInt", "jsonDecodeIntFromIntOrBool"):
                self.assertIn(decoder, block, path)
            self.assertIn("Json.Decode.bool", block, path)
            self.assertIn("Json.Decode.int", block, path)


class ExposedAndNotActedOnTest(unittest.TestCase):
    """The whole scope of #35, asserted rather than described in a comment.

    The issue is explicit that nobody knows yet which field means "still
    cycling", and #38 shipped a deadline designed to survive these fields being
    worthless precisely because of it. Wiring one into a decision on the
    strength of a no-target sample is the mistake twice over, so the source is
    checked for it.
    """

    def setUp(self):
        self.source = bot_elm()
        # Prose about these fields is expected and encouraged; a *read* of one
        # is what must not spread. `{- -}` blocks are this file's doc comments.
        self.code = re.sub(r"\{-.*?-\}", "", self.source, flags=re.DOTALL)

    def function_body(self, signature_start, source=None):
        source = self.source if source is None else source
        start = source.index(signature_start)
        end = source.index("\n\n\n", start)
        return source[start:end]

    def test_nothing_but_the_status_line_reads_them(self):
        describe = self.function_body(
            "describeTopRowModuleDictState : ReadingFromGameClient", self.code)
        self.assertEqual(
            self.code.count("stateFromDictEntries"),
            describe.count("stateFromDictEntries"),
            "something outside describeTopRowModuleDictState reads the module "
            "button's dict entries -- #35 exposes them to be logged, and the "
            "one leg #34 needed (isDeactivating going True) has still never "
            "been observed")

    def test_the_meanings_of_the_old_fields_are_unchanged(self):
        # `isActive` still reads `ramp_active` through the parser, and the
        # keep-active filter still consults `isActive`. Repointing either at a
        # new field is the change this issue explicitly defers.
        self.assertIn(
            "|> List.filter (.isActive >> Maybe.withDefault False >> not)",
            self.source)

    def test_the_status_line_names_the_four_fields_the_issue_asks_for(self):
        describe = self.function_body("describeTopRowModuleDictState : ReadingFromGameClient")
        for key in KEYS_IN_THE_STATUS_LINE:
            self.assertIn(key, describe, key)

    def test_the_line_is_printed_every_reading(self):
        # In `describeMenuAndSettlingCounters`, beside the middle-row line --
        # the part of the status text that goes out on every reading rather
        # than only in some branch. A field logged only when some decision
        # happens to run is not a record anyone can read a run back from, which
        # is the whole deliverable here.
        start = self.source.index("        describeMenuAndSettlingCounters =")
        end = self.source.index("        describeCurrentReading =", start)
        counters = self.source[start:end]
        self.assertIn("describeTopRowModuleDictState readingFromGameClient", counters)

    def test_it_reports_the_row_the_guns_are_in(self):
        describe = self.function_body("describeTopRowModuleDictState : ReadingFromGameClient")
        self.assertIn("moduleButtonsRows.top", describe)

    def test_absent_false_and_zero_all_print_differently(self):
        # Three distinct outputs, because they are three distinct facts and two
        # of the three transitions between them were seen live: `ramp_active`
        # going absent -> present, and oscillating True/False once present.
        # Reading a run's log back is exactly when a collapsed pair cannot be
        # told apart again.
        describe = self.function_body("describeTopRowModuleDictState : ReadingFromGameClient")
        for rendering in ('"-"', '"F"', '"T"', "String.fromInt number"):
            self.assertIn(rendering, describe, rendering)

    def test_the_missing_leg_would_be_recorded(self):
        # `isDeactivating` going `True` is the one observation nobody has, and
        # the next ammo swap is what produces it. It has to be in the line that
        # prints unconditionally, beside the switched-on flag that says whether
        # the module was on when it happened.
        describe = self.function_body("describeTopRowModuleDictState : ReadingFromGameClient")
        self.assertIn("stateFromDictEntries.isDeactivating", describe)
        self.assertIn("stateFromDictEntries.isInActiveState", describe)

    def test_the_row_is_ordered_by_position_not_by_index(self):
        # The row list is not a stable index space -- a slot leaves and rejoins
        # whenever its display region cannot be read. Two readings sorted
        # differently would put one gun's values in another's column, which is
        # the kind of defect that only shows up when someone tries to use the
        # table months later.
        describe = self.function_body("describeTopRowModuleDictState : ReadingFromGameClient")
        self.assertIn("List.sortBy (.uiNode >> .totalDisplayRegion >> .x)", describe)


if __name__ == "__main__":
    unittest.main()
