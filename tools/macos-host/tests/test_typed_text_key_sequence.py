"""What happens to a typed string between the bot and `CGEventPost`.

Issue #75 reports `Emperor Family Bureau` arriving in the client's search bar as
`eueu` and names three places it could be lost: `effectsToEnterString`, the
virtual-key table in `botlab_host.py`, and `cg_input`. These cases execute the
first two over the strings the bot really types.

**They do not lose anything, and the first suspect is not even in the path.**
The mission runner's search bar is typed by `Bot.elm`'s own `typeTextEffects`,
which emits one `KeyDown`/`KeyUp` pair per character and presses no modifier at
all -- so the shift-state tracking #75 points at never runs. Driving the real
`_windows_input` over the real sequence shape posts every character, in order,
with the right `CGKeyCode` and the shipped 30ms hold and 210ms gap.

What the cases here pin is therefore two things rather than one.

The **finding**: the loss is below the layers the issue names. The corpus says
where -- runs 17 and 19, the two that lost the query, posted every event an
order of magnitude more slowly than every other recorded run, with no overlap
across the whole corpus. That is a saturated posting path, not a mapping or a
pacing rule, and nothing in the log said so.

The **fix**: a key a sequence presses and does not release stayed down for the
rest of the session. `_keys_down` was written on every `KeyDown` and read
nowhere. `effectsToEnterString` builds exactly that sequence -- it releases
Shift only when the *next* character does not want it, so a string ending in a
capital ends with Shift down -- and `getKeyboardKeyToEnterChar` could put
**Command** underneath the typing, having mapped `[` to `vkey_LWIN` through an
off-by-one. That is the failure mode this issue describes: every effect
dispatched, every event posted, and the characters gone, because the client was
reading shortcuts.
"""
import io
import os
import re
import sys
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402
from prerequisites import recorded_runs  # noqa: E402

EFFECT_ON_WINDOW_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Common", "EffectOnWindow.elm")

# The framework's own spacing. `EveOnline/BotFramework.elm`'s
# `buildTaskFromEffectSequence` prepends a BringWindowToForeground and a
# WaitMilliseconds 100, then intersperses a WaitMilliseconds 210 between every
# pair of effects. Written here because the item list is the protocol between
# the two sides, not a rule either of them owns.
FRAMEWORK_SPACING_MS = 210
FRAMEWORK_FOREGROUND_WAIT_MS = 100

# Windows virtual-key codes, from the same table `Bot.elm`'s
# `virtualKeyCodeForTypedCharacter` uses: for an ASCII letter, digit or space the
# virtual-key code *is* the character's own uppercase code point.
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_SPACE = 0x20
VK_LWIN = 0x5B

# macOS `kVK_ANSI_*` from HIToolbox/Events.h, written out independently of the
# host's own table so a typo in either one is a disagreement rather than a
# shared mistake. Neither side is contiguous, which is why the host cannot map
# arithmetically and why this has to be checked character by character.
KVK_FOR_LETTER = {
    "A": 0x00, "B": 0x0B, "C": 0x08, "D": 0x02, "E": 0x0E, "F": 0x03,
    "G": 0x05, "H": 0x04, "I": 0x22, "J": 0x26, "K": 0x28, "L": 0x25,
    "M": 0x2E, "N": 0x2D, "O": 0x1F, "P": 0x23, "Q": 0x0C, "R": 0x0F,
    "S": 0x01, "T": 0x11, "U": 0x20, "V": 0x09, "W": 0x0D, "X": 0x07,
    "Y": 0x10, "Z": 0x06,
}
KVK_FOR_DIGIT = {
    "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "5": 0x17, "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
}
KVK_SPACE = 0x31
KVK_RETURN = 0x24
KVK_SHIFT = 0x38
KVK_COMMAND = 0x37

# The two queries the failing runs typed, and a third the corpus shows landing.
RUN_19_QUERY = "Emperor Family Bureau"
RUN_17_QUERY = "Emperor Family Academy"
LONG_FILTER = "Small Sealed Cargo Containers"


def collapsed(source):
    """The source with runs of whitespace collapsed, for reading structure.

    `elm-format` moves line breaks around inside an expression, and #58 broke
    three cases that had matched the old layout. Nothing here matches a newline.
    """
    return re.sub(r"\s+", " ", source)


def effect_on_window_source():
    with open(EFFECT_ON_WINDOW_ELM, encoding="utf-8") as source:
        return source.read()


def definition_body(source, name):
    """A top-level definition's body, from its `=` to the next top-level form."""
    start = re.search(r"^" + re.escape(name) + r"\b[^\n]*=\n", source, re.M)
    assert start is not None, "no definition of %s in EffectOnWindow.elm" % name
    rest = source[start.end():]
    end = re.search(r"\n\n\n", rest)
    return rest[:end.start()] if end else rest


def vk_for_typed_character(char):
    """The virtual-key code `typeTextEffects` emits for `char`, or None.

    The rule it mirrors is one line of `Bot.elm` and is *not* read from there:
    that file is where the bots are edited, and a case that reads it would be
    asserting the host against whatever the bot happens to say today rather than
    against the protocol they agree on.
    """
    code = ord(char.upper())
    if 0x41 <= code <= 0x5A or 0x30 <= code <= 0x39 or code == 0x20:
        return code
    return None


def typed_text_effects(text):
    """The effects `Bot.elm`'s `typeTextEffects` builds for `text`."""
    effects = []
    for char in text:
        vk = vk_for_typed_character(char)
        if vk is None:
            continue
        effects += [{"KeyDown": [vk, False]}, {"KeyUp": [vk, False]}]
    return effects


def as_input_items(effects, foreground=True):
    """The `WindowsInputSequenceItem` list the framework sends for `effects`."""
    items = []
    if foreground:
        items += [{"BringWindowToForeground": "winapi/1"},
                  {"WaitMilliseconds": FRAMEWORK_FOREGROUND_WAIT_MS}]
    for index, effect in enumerate(effects):
        if index:
            items.append({"WaitMilliseconds": FRAMEWORK_SPACING_MS})
        items.append(effect)
    return items


def search_bar_effects(query):
    """The mission runner's own search sequence: click, type, press Return.

    The shape is `Bot.elm`'s -- `mouseClickOnUIElement`, then `typeTextEffects`,
    then a Return pair -- and it is the sequence runs 17 and 19 dispatched.
    """
    return ([{"MouseMoveAbsolute": [128, 89]},
             {"ButtonDown": 0x01},
             {"ButtonUp": 0x01}]
            + typed_text_effects(query)
            + [{"KeyDown": [VK_RETURN, False]}, {"KeyUp": [VK_RETURN, False]}])


def shift_held_effects(text):
    """`effectsToEnterString`'s shape for an all-capitals string.

    Shift is pressed once and the letters follow underneath it -- and, before
    this change, nothing released it. Built here rather than executed through
    `elm repl` because what is being pinned is the *host's* answer to a sequence
    of this shape, which it must give whatever built it.
    """
    effects = [{"KeyDown": [VK_SHIFT, False]}]
    for char in text:
        vk = ord(char.upper())
        effects += [{"KeyDown": [vk, False]}, {"KeyUp": [vk, False]}]
    return effects


class Recorder:
    """A stand-in for `cg_input`, so a case can read what was posted.

    Nothing here reaches a real `CGEventPost`: the whole point of these cases is
    that the host's answer can be established without putting one keystroke into
    a live client.
    """

    def __init__(self, fail_on=None):
        self.posted = []
        self.slept = []
        self.fail_on = fail_on

    def cg(self, command):
        if self.fail_on is not None and command == self.fail_on:
            # Once, so the case can watch the release land afterwards. A
            # `cg_input` that stays dead is covered by the host catching the
            # release too, which `_windows_input` reports rather than raises.
            self.fail_on = None
            raise OSError("cg_input went away")
        self.posted.append(command)
        return "ok"

    def keys(self):
        return [command for command in self.posted
                if command.startswith(("keydown ", "keyup "))]


def dispatch(items, fail_on=None):
    """Run the real `_windows_input` over `items`, posting nothing."""
    dispatcher = botlab_host.TaskDispatcher.__new__(botlab_host.TaskDispatcher)
    dispatcher.execute_input = True
    dispatcher._buttons_down = set()
    dispatcher._keys_down = []
    dispatcher._scale_x = 1.0
    dispatcher._scale_y = 1.0
    dispatcher._last_mouse_pos = (0.0, 0.0)
    dispatcher._last_input_post_at = 0.0
    dispatcher._glide_costs_this_step = []
    dispatcher.volatile = types.SimpleNamespace(game_pid=1234)

    recorder = Recorder(fail_on=fail_on)
    dispatcher._cg = recorder.cg
    dispatcher._cg_move = lambda x, y: recorder.posted.append(
        "move %.1f %.1f" % (x, y))
    dispatcher._seconds_since_human_input = lambda: 100.0

    saved = (botlab_host.bring_window_to_foreground,
             botlab_host._window_is_onscreen, time.sleep)
    botlab_host.bring_window_to_foreground = lambda pid, window: True
    botlab_host._window_is_onscreen = lambda window: True
    time.sleep = recorder.slept.append
    noise = io.StringIO()
    stderr, sys.stderr = sys.stderr, noise
    try:
        response = dispatcher._windows_input(items)["WindowsInputResponse"]
    finally:
        sys.stderr = stderr
        (botlab_host.bring_window_to_foreground,
         botlab_host._window_is_onscreen, time.sleep) = saved
    return dispatcher, recorder, response, noise.getvalue()


def typed_back(recorder):
    """The characters the posted `keydown` commands spell, in order."""
    by_mac_code = {mac: vk for vk, mac in botlab_host._VK_TO_CGKEYCODE.items()}
    spelled = []
    for command in recorder.keys():
        if not command.startswith("keydown "):
            continue
        vk = by_mac_code[int(command.split()[1])]
        spelled.append(chr(vk) if vk != VK_RETURN else "\n")
    return "".join(spelled)


class TheKeyTableCoversEverythingThatCanBeTypedTest(unittest.TestCase):
    """The mapping half of #75's "any of those three can drop"."""

    def test_every_typable_character_has_a_macos_key(self):
        for char in [chr(code) for code in range(0x41, 0x5B)] + \
                [chr(code) for code in range(0x30, 0x3A)] + [" "]:
            vk = vk_for_typed_character(char)
            self.assertIsNotNone(
                botlab_host.vk_to_cgkeycode(vk),
                "no macOS key for %r, which typeTextEffects emits as VK 0x%02X"
                % (char, vk))

    def test_the_table_agrees_with_the_standard_us_layout(self):
        for letter, kvk in KVK_FOR_LETTER.items():
            self.assertEqual(botlab_host.vk_to_cgkeycode(ord(letter)), kvk,
                             "letter %s maps to the wrong CGKeyCode" % letter)
        for digit, kvk in KVK_FOR_DIGIT.items():
            self.assertEqual(botlab_host.vk_to_cgkeycode(ord(digit)), kvk,
                             "digit %s maps to the wrong CGKeyCode" % digit)
        self.assertEqual(botlab_host.vk_to_cgkeycode(VK_SPACE), KVK_SPACE)
        self.assertEqual(botlab_host.vk_to_cgkeycode(VK_RETURN), KVK_RETURN)
        self.assertEqual(botlab_host.vk_to_cgkeycode(VK_SHIFT), KVK_SHIFT)

    def test_the_windows_key_is_command_here(self):
        """Which is what made `getKeyboardKeyToEnterChar`'s off-by-one costly.

        The mapping itself is deliberate -- the editing shortcuts a macOS field
        answers to are Command-based -- so the fix belongs on the Elm side that
        was reaching for it, not here.
        """
        self.assertEqual(botlab_host.vk_to_cgkeycode(VK_LWIN), KVK_COMMAND)


class TheHostPostsEveryCharacterTest(unittest.TestCase):
    """#75's "nineteen characters went in, four came out", asked of the host."""

    def test_run_19s_query_is_posted_whole(self):
        _, recorder, response, _ = dispatch(
            as_input_items(search_bar_effects(RUN_19_QUERY)))
        self.assertEqual(typed_back(recorder), RUN_19_QUERY.upper() + "\n")
        self.assertEqual(response["errorMessages"], [])
        self.assertEqual(response["abortedStepsCount"], 0)

    def test_run_17s_query_is_posted_whole(self):
        _, recorder, _, _ = dispatch(
            as_input_items(search_bar_effects(RUN_17_QUERY)))
        self.assertEqual(typed_back(recorder), RUN_17_QUERY.upper() + "\n")

    def test_a_long_filter_string_is_posted_whole(self):
        _, recorder, _, _ = dispatch(
            as_input_items(typed_text_effects(LONG_FILTER)))
        self.assertEqual(typed_back(recorder), LONG_FILTER.upper())

    def test_every_press_has_its_release(self):
        _, recorder, _, _ = dispatch(
            as_input_items(search_bar_effects(RUN_19_QUERY)))
        commands = recorder.keys()
        self.assertEqual(len(commands), 2 * (len(RUN_19_QUERY) + 1))
        for down, up in zip(commands[0::2], commands[1::2]):
            self.assertTrue(down.startswith("keydown "), down)
            self.assertEqual(up, down.replace("keydown", "keyup", 1))

    def test_the_spaces_are_posted_too(self):
        """The two failing queries carry spaces and the landing ones did not,
        which is the first thing a per-character theory would reach for."""
        _, recorder, _, _ = dispatch(
            as_input_items(typed_text_effects("A B")))
        self.assertEqual(
            [command for command in recorder.keys() if command.startswith("keydown")],
            ["keydown %d" % KVK_FOR_LETTER["A"],
             "keydown %d" % KVK_SPACE,
             "keydown %d" % KVK_FOR_LETTER["B"]])


class ThePacingIsTheShippedOneTest(unittest.TestCase):
    """#75's pacing hypothesis, asked of the code that decides the pacing."""

    def test_a_key_is_held_briefly_and_the_gap_is_the_frameworks(self):
        _, recorder, _, _ = dispatch(
            as_input_items(typed_text_effects("ABC")))
        gaps = [value for value in recorder.slept if value >= 0.02]
        self.assertEqual(
            gaps,
            [FRAMEWORK_FOREGROUND_WAIT_MS / 1000.0,
             botlab_host.KEY_HOLD_SECONDS, FRAMEWORK_SPACING_MS / 1000.0,
             botlab_host.KEY_HOLD_SECONDS, FRAMEWORK_SPACING_MS / 1000.0,
             botlab_host.KEY_HOLD_SECONDS])

    def test_the_hold_is_short_enough_not_to_repeat_and_long_enough_to_land(self):
        """Both bounds, and a fixed value either side of each.

        A case that only compares the constant to itself passes for any
        constant, which is the hole four of #120's cases had.
        """
        self.assertGreater(botlab_host.KEY_HOLD_SECONDS, 0.0)
        self.assertGreaterEqual(botlab_host.KEY_HOLD_SECONDS, 0.01)
        self.assertLess(botlab_host.KEY_HOLD_SECONDS, 0.25)
        self.assertLessEqual(botlab_host.KEY_HOLD_SECONDS, 0.12)

    def test_a_held_shift_does_not_collapse_the_gaps_between_characters(self):
        """#71's own regression, re-asserted where the shape comes from.

        Scoping the skip to "any key is held" would fire the characters back to
        back underneath the Shift, which is the shape that loses keystrokes.
        """
        _, recorder, _, _ = dispatch(
            as_input_items(shift_held_effects("AB"), foreground=False))
        gaps = [value for value in recorder.slept if value >= 0.02]
        self.assertEqual(gaps.count(FRAMEWORK_SPACING_MS / 1000.0), 2)
        self.assertEqual(gaps.count(botlab_host.KEY_HOLD_SECONDS), 2)


class AKeyLeftHeldIsTakenBackTest(unittest.TestCase):
    """The fix. `_keys_down` was written on every press and read nowhere."""

    def test_a_balanced_sequence_leaves_nothing_held(self):
        self.assertEqual(
            botlab_host.keys_left_held(
                as_input_items(search_bar_effects(RUN_19_QUERY))),
            [])

    def test_effects_to_enter_strings_shape_leaves_shift_held(self):
        self.assertEqual(
            botlab_host.keys_left_held(
                as_input_items(shift_held_effects("AB"))),
            [KVK_SHIFT])

    def test_a_chord_that_releases_its_modifiers_leaves_nothing(self):
        """The lock chord -- Ctrl held over a click -- is balanced and must not
        be reported."""
        effects = [{"KeyDown": [0x11, False]},
                   {"MouseMoveAbsolute": [10, 10]},
                   {"ButtonDown": 0x01},
                   {"ButtonUp": 0x01},
                   {"KeyUp": [0x11, False]}]
        self.assertEqual(botlab_host.keys_left_held(as_input_items(effects)), [])

    def test_an_unmapped_key_never_counts_as_held(self):
        """A VK code with no macOS key is reported as an error and posted
        nowhere, so it cannot be holding anything down."""
        self.assertEqual(
            botlab_host.keys_left_held([{"KeyDown": [0xFF, False]}]), [])

    def test_the_order_is_the_presses(self):
        effects = [{"KeyDown": [0x11, False]}, {"KeyDown": [VK_SHIFT, False]}]
        self.assertEqual(
            botlab_host.keys_left_held(as_input_items(effects)),
            [botlab_host.vk_to_cgkeycode(0x11), KVK_SHIFT])

    def test_the_release_is_posted_and_the_host_forgets_the_key(self):
        dispatcher, recorder, _, _ = dispatch(
            as_input_items(shift_held_effects("AB")))
        self.assertEqual(recorder.keys()[-1], "keyup %d" % KVK_SHIFT)
        self.assertEqual(dispatcher._keys_down, [])

    def test_the_release_undoes_the_presses_in_reverse(self):
        effects = [{"KeyDown": [0x11, False]}, {"KeyDown": [VK_SHIFT, False]}]
        _, recorder, _, _ = dispatch(as_input_items(effects))
        self.assertEqual(
            recorder.keys()[-2:],
            ["keyup %d" % KVK_SHIFT,
             "keyup %d" % botlab_host.vk_to_cgkeycode(0x11)])

    def test_a_balanced_sequence_posts_no_extra_release(self):
        _, recorder, _, _ = dispatch(
            as_input_items(search_bar_effects(RUN_19_QUERY)))
        self.assertEqual(len(recorder.keys()), 2 * (len(RUN_19_QUERY) + 1))

    def test_it_says_so(self):
        _, _, _, said = dispatch(as_input_items(shift_held_effects("AB")))
        self.assertIn("KEYS LEFT HELD", said)
        self.assertIn(str(KVK_SHIFT), said)

    def test_a_balanced_sequence_says_nothing(self):
        _, _, _, said = dispatch(
            as_input_items(search_bar_effects(RUN_19_QUERY)))
        self.assertNotIn("KEYS LEFT HELD", said)

    def test_a_press_whose_release_never_posted_is_still_taken_back(self):
        """The half `keys_left_held` cannot see.

        A `cg_input` that dies between a press and its release leaves the key
        down while the sequence itself was perfectly balanced, so the release
        has to be driven by what was posted rather than by the item list.
        """
        items = as_input_items(typed_text_effects("A"))
        dispatcher, recorder, _, said = dispatch(
            items, fail_on="keyup %d" % KVK_FOR_LETTER["A"])
        self.assertEqual(botlab_host.keys_left_held(items), [])
        self.assertEqual(dispatcher._keys_down, [])
        self.assertIn("KEYS LEFT HELD", said)


class TheElmSideReleasesItsShiftTest(unittest.TestCase):
    """Read out of the source: `effectsToEnterString` is called by no bot, so
    there is nothing to execute it through and no run that exercises it."""

    @classmethod
    def setUpClass(cls):
        cls.source = effect_on_window_source()
        cls.flat = collapsed(cls.source)

    def test_the_fold_ends_by_releasing_shift(self):
        body = collapsed(definition_body(self.source, "effectsToEnterString"))
        self.assertIn("Result.map releaseShiftAtTheEnd", body)
        self.assertNotIn("Result.map Tuple.second", body)

    def test_the_release_presses_nothing_and_raises_shift(self):
        body = collapsed(definition_body(self.source, "releaseShiftAtTheEnd"))
        self.assertIn("if state.shiftKeyIsDown then", body)
        self.assertIn("effects ++ [ KeyUp vkey_SHIFT ]", body)
        self.assertNotIn("KeyDown", body)

    def test_neither_letter_range_admits_a_twenty_seventh_letter(self):
        """`<= 26` is one past `z` and one past `Z`, and both land on
        `vkey_LWIN`."""
        body = collapsed(definition_body(self.source, "getKeyboardKeyToEnterChar"))
        self.assertIn("relativeToLetterLower < 26 then", body)
        self.assertIn("relativeToLetterUpper < 26 then", body)
        self.assertNotIn("<= 26", body)

    def test_no_character_is_typed_by_pressing_command(self):
        body = collapsed(definition_body(self.source, "getKeyboardKeyToEnterChar"))
        self.assertNotIn("vkey_LWIN", body)

    def test_the_argument_is_written_down_where_it_is_read(self):
        """The doc comment carries why, because the next reader of this file is
        the one who would restore the shorter bound."""
        self.assertIn("vkey_LWIN", self.flat)
        self.assertIn("keys_left_held", self.flat)


class TheCorpusSaysWhereTheLossIsNotTest(unittest.TestCase):
    """Relations, recounted from the runs, rather than the numbers above."""

    GLIDE = re.compile(r"^#\s+move: .*\bin (\d+\.\d+)s\s*$", re.M)

    def glides(self, path):
        with open(path, encoding="utf-8", errors="replace") as handle:
            return [float(value) for value in self.GLIDE.findall(handle.read())]

    def test_the_two_failing_runs_posted_events_far_more_slowly(self):
        """A glide is ten posted `move` commands and nine sleeps of 25ms, so its
        duration measures what one posted event costs -- and the two runs that
        lost the query separate from every other recorded run with no overlap at
        all. That is the posting path being saturated, which is below every
        layer #75 names.
        """
        failing = []
        for _, path in recorded_runs("17", "19"):
            failing += self.glides(path)
        healthy = []
        for _, path in recorded_runs("27", "29", "30", "31", "34", "35", "36", "37"):
            healthy += self.glides(path)
        self.assertGreater(len(failing), 20, "no glides recorded in run 17 or 19")
        self.assertGreater(len(healthy), 200, "no glides recorded in the later runs")
        self.assertGreater(min(failing), max(healthy),
                           "the two runs that lost the query must be separable "
                           "from the rest by what a posted event cost")

    def test_the_mangled_query_is_confined_to_those_two_runs(self):
        """The give-up that follows a search whose results cannot hold the
        station. Absence in the later runs is weaker evidence than presence in
        these two -- since #69 the bot prefers ESI and reaches the search bar
        less often -- so this is asserted as a relation and not as a cure.
        """
        # Gated on the two runs #75 is about rather than on the ten together:
        # a machine holding only the later runs would otherwise find no
        # give-up anywhere and report that as the issue's own evidence having
        # vanished, which is `recorded_runs`' documented trap.
        carried = 0
        for _, path in recorded_runs("17", "19"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                carried += handle.read().count("The search results do not offer")
        self.assertGreater(carried, 0,
                           "runs 17 and 19 must carry the give-up #75 was filed on")
        for name, path in recorded_runs("27", "29", "30", "31", "34", "35",
                                        "36", "37"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                self.assertEqual(
                    handle.read().count("The search results do not offer"), 0,
                    "run %s also failed a search, which would mean the shape "
                    "outlived those two runs" % name)

    def test_a_long_string_with_spaces_did_land_in_a_later_run(self):
        """The quick filter is the one typed field the bot reads back: it moves
        on once the box holds a prefix of what it typed. A run that typed a
        15- and a 29-character name with spaces and did not have to retype is a
        run whose typing arrived.
        """
        for name, path in recorded_runs("30", "34", "37"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            typings = re.findall(r"Filter the inventory for '([^']*)'", text)
            self.assertTrue(typings, "run %s must have filtered something" % name)
            longest = max(typings, key=len)
            self.assertGreater(len(longest), 4)
            # One reading emits several decision lines, so the count that means
            # "retyped" is the number of *distinct readings*, which the repeated
            # line cannot distinguish -- what is asserted instead is that the
            # bot never had to clear the box and start again.
            self.assertEqual(text.count("The quick filter holds something else"), 0,
                             "run %s had to clear a filter it had typed" % name)


if __name__ == "__main__":
    unittest.main()
