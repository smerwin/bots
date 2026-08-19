"""Tests for the character name the console shows.

Issue #310: the console named the bot and never the pilot. Its own page comment
says the app name is in the tab title "because two consoles open at once are
otherwise the same tab twice" -- and that is exactly the problem one level in,
because the app name is the bot directory's leaf and both Windows hosts fly
`eve-online-saxrat`. Two saxrat consoles were the same page twice: same title,
same header, different character, and nothing on the page saying which.

The name was never missing, only unrouted. The client titles its window
`EVE - <character>`; `find_eve_processes` captures it as `mainWindowTitle`, the
volatile host keeps it as `game_window_title`, and
`esi_waypoint.character_from_window_title` parses it. Its only reader was the
ESI destination guard, which refuses to route a *different* character than the
bot is flying -- so the name was already trusted enough to block a live action
and still never reached the operator watching the run.

**Two rules carry most of these cases, and both are about absence.**

  - A reading that cannot name a character is the host saying *cannot tell*, not
    the client changing pilot. `character_from_window_title` answers `None` for
    a window with no name -- including `find_eve_processes`' own `"EVE"`
    fallback -- and `set_destination` reads that as "cannot check" rather than
    as a mismatch. The console follows the same rule: an absent name never
    erases one an earlier reading established.
  - The page says it does not know rather than showing a blank, which is
    `loadRefusalFromGameLog`'s register applied to an identity field.

The console cases are *executed* against a real `ConsoleState` and a real
`snapshot()`, and the title cases through the real `character_from_window_title`,
because a Python restatement of either would only test the restatement. The two
that read source are the wiring and the page, neither of which can be executed
from here. Nothing here reads `~/eve-bot-logs`, a live client or a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
sys.path.insert(0, MACOS_HOST_DIR)

import esi_waypoint  # noqa: E402
import web_console  # noqa: E402

HOST_SOURCE = os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py")
CONSOLE_PAGE = os.path.join(MACOS_HOST_DIR, "web_console.html")

# The title a real client carries, from `MACOS.md` and the fixture in
# `test_eve_repl.py`. The character is whatever follows the separator.
A_REAL_TITLE = "EVE - Gal Bistot"


def collapse(path):
    """Whitespace-collapsed source, so reformatting cannot break an assertion."""
    with open(path) as f:
        return re.sub(r"\s+", " ", f.read())


def host_lines(state):
    """The console's own lines, which is where a character change is announced."""
    return [line["text"] for line in state.snapshot()["lines"]
            if line["kind"] == "host"]


class TheConsoleCarriesTheCharacterTest(unittest.TestCase):
    """A real `ConsoleState`, told a name the way the bot loop tells it."""

    def setUp(self):
        self.state = web_console.ConsoleState()

    def test_a_console_nobody_has_told_names_nobody(self):
        # Empty rather than absent: the page distinguishes "no character yet"
        # from a field it does not understand, and a missing key would be the
        # latter.
        self.assertEqual(self.state.snapshot()["character"], "")

    def test_the_name_reaches_the_snapshot(self):
        self.state.note_character("Gal Bistot")
        self.assertEqual(self.state.snapshot()["character"], "Gal Bistot")

    def test_the_name_is_announced_once_and_not_once_a_reading(self):
        # The bot loop calls this on every pass, so a line per call would be a
        # line per reading for the rest of the session -- thousands of them,
        # burying the decisions the log exists for.
        for _ in range(50):
            self.state.note_character("Gal Bistot")
        self.assertEqual(host_lines(self.state), ["flying Gal Bistot"])

    def test_a_reading_that_cannot_tell_does_not_erase_the_name(self):
        # `None` is "cannot check", which is what the ESI guard reads it as. A
        # client whose title goes missing for one reading has not changed pilot.
        self.state.note_character("Gal Bistot")
        self.state.note_character(None)
        self.assertEqual(self.state.snapshot()["character"], "Gal Bistot")

    def test_an_empty_name_does_not_erase_the_name_either(self):
        self.state.note_character("Gal Bistot")
        self.state.note_character("")
        self.assertEqual(self.state.snapshot()["character"], "Gal Bistot")

    def test_nothing_is_announced_for_a_name_that_never_arrives(self):
        self.state.note_character(None)
        self.state.note_character("")
        self.assertEqual(host_lines(self.state), [])
        self.assertEqual(self.state.snapshot()["character"], "")

    def test_a_different_character_replaces_it_and_says_so(self):
        # Worth a line rather than a silent swap: the console is now watching
        # something else, and the log above the change describes another pilot.
        self.state.note_character("Gal Bistot")
        self.state.note_character("Nal Bistot")
        self.assertEqual(self.state.snapshot()["character"], "Nal Bistot")
        self.assertEqual(host_lines(self.state),
                         ["flying Gal Bistot", "now flying Nal Bistot"])

    def test_the_identity_the_console_already_had_is_untouched(self):
        # The three fixed fields are resolved before the console exists and the
        # character is not; adding the fourth must not disturb them.
        state = web_console.ConsoleState(app_name="eve-online-saxrat",
                                         bot_source="/x/eve-online-saxrat",
                                         version="0057425 (clean)")
        state.note_character("Gal Bistot")
        snapshot = state.snapshot()
        self.assertEqual(snapshot["appName"], "eve-online-saxrat")
        self.assertEqual(snapshot["version"], "0057425 (clean)")
        self.assertEqual(snapshot["character"], "Gal Bistot")


class TheNameComesFromTheWindowTitleTest(unittest.TestCase):
    """Through the real parser, and composed the way the host composes it."""

    def flown(self, title):
        """What the console ends up showing for a client titled `title`."""
        state = web_console.ConsoleState()
        state.note_character(esi_waypoint.character_from_window_title(title))
        return state.snapshot()["character"]

    def test_a_real_client_title_names_its_character(self):
        self.assertEqual(self.flown(A_REAL_TITLE), "Gal Bistot")

    def test_the_untitled_fallback_names_nobody(self):
        # `find_eve_processes` substitutes the literal "EVE" when the window has
        # no name, and that is a fallback rather than a character. Showing it
        # would be a console confidently naming a pilot who does not exist.
        self.assertEqual(self.flown("EVE"), "")

    def test_a_window_with_no_title_at_all_names_nobody(self):
        self.assertEqual(self.flown(None), "")

    def test_a_title_that_arrives_late_still_names_the_character(self):
        # The ordering this whole wiring exists for: the console serves several
        # readings before any client list has been answered.
        state = web_console.ConsoleState()
        for _ in range(5):
            state.note_character(esi_waypoint.character_from_window_title(None))
        self.assertEqual(state.snapshot()["character"], "")
        state.note_character(esi_waypoint.character_from_window_title(A_REAL_TITLE))
        self.assertEqual(state.snapshot()["character"], "Gal Bistot")
        self.assertEqual(host_lines(state), ["flying Gal Bistot"])


class TheHostTellsTheConsoleTest(unittest.TestCase):
    """The wiring, which cannot be executed from here without a client."""

    def setUp(self):
        self.source = collapse(HOST_SOURCE)

    def test_the_loop_pushes_the_character_to_the_console(self):
        self.assertIn("console.note_character(", self.source)

    def test_it_reads_the_same_title_the_esi_guard_reads(self):
        # One field, two readers. A second source for "who are we flying" is
        # exactly the divergence this repo keeps a section on.
        self.assertIn(
            "console.note_character(esi_waypoint.character_from_window_title( "
            "dispatcher.volatile.game_window_title))",
            self.source)

    def test_the_character_is_not_a_constructor_argument(self):
        # It cannot be: the console is built before the bot has asked for the
        # client list, so a fourth fixed field would be permanently empty.
        constructor = self.source[self.source.index("web_console.ConsoleState("):]
        constructor = constructor[:constructor.index(")")]
        self.assertNotIn("character", constructor)


class ThePageShowsTheCharacterTest(unittest.TestCase):
    def setUp(self):
        self.page = collapse(CONSOLE_PAGE)

    def test_the_page_has_a_place_for_it(self):
        self.assertIn('id="character"', self.page)
        self.assertIn("s.character", self.page)

    def test_the_tab_title_carries_the_character(self):
        # The app name alone does not tell two saxrat consoles apart, which is
        # the whole of #310.
        self.assertIn("document.title = `${character}", self.page)

    def test_the_page_says_unknown_rather_than_showing_a_blank(self):
        self.assertIn("character unknown", self.page)

    def test_the_character_is_re_read_rather_than_identified_once(self):
        # `identify()` returns early forever after its first call, so a name
        # that arrives later would never be shown if it were read there.
        identify = self.page[self.page.index("function identify(s){"):]
        identify = identify[:identify.index("function nameCharacter")]
        self.assertNotIn("s.character", identify)
        self.assertIn("nameCharacter(s);", self.page)


if __name__ == "__main__":
    unittest.main()
