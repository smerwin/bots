"""What modifiers the events `cg_input` posts actually carry.

Issue #240. Every event in `cg_input.c` was created with a `NULL` source and
posted without its flags ever being set -- `CGEventSetFlags` occurred zero times
in the file -- and an event created that way is **born carrying the session's
current modifier state**.

That premise was the issue's own load-bearing guess, and it is now measured. A
sampler reading `CGEventSourceFlagsState(kCGEventSourceStateCombinedSessionState)`
and, in the same breath, the flags on an unposted
`CGEventCreateKeyboardEvent(NULL, kVK_ANSI_Q, true)` agreed on **390 of 390
samples across nine transitions of the Fn/Globe bit**. The event does not
sample the session once at startup or approximately: it is the session, at the
instant of creation.

What that cost is in the issue: with Fn set, the letters this bot presses are
Globe chords rather than letters -- `Q` is Quick Note, `E` the emoji picker,
`C` Control Centre, `F` toggle-full-screen.

**And the Fn is the bot's own.** Sampled with nobody at the machine, the bit
reads set on 100% of 2,178 samples while a run is going and 0% of 1,976 with
the run stopped -- so it is neither a stuck key nor ambient state. macOS marks
F1-F4, the arrows and the navigation block as Fn keys by convention, and this
bot posts F1-F4 as weapon hotkeys; measured on a *clean* session, a
private-source F1 reads 0x20800000 and a private-source `Q` reads 0x20000000,
so the bit is the key's own. Its own F1 asserts Fn into the session and every
later event inherits it.

**So neither clearing nor keeping the flags is right.** Clearing them breaks
`Ctrl+click`, which is how the bot locks a target, and `Ctrl+Shift+click`,
which is how it unlocks -- `lockClickLocationFromStepEffects` recognises a lock
attempt by exactly that chord -- and it would strip the Fn that F1 is entitled
to, which could stop F1 registering as F1. Keeping them is the leak itself.
Each event carries what the key itself carries, read off a private-source twin
rather than restated from a table, plus what `cg_input` is deliberately
holding, and nothing that merely happened to be in the session.

Two layers, because the failure has two halves.

`input_flags.h` holds the composition rule and is compiled here on any machine
with a C compiler, so the mask itself is checked on every push. The real
`cg_input` binary is then driven through `--dry-run`, which composes and
reports every event and posts none of them -- the only way to assert on what
this program would put on the wire without putting it there, on a machine where
what is frontmost is usually a live client.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
CG_INPUT_DIR = os.path.join(MACOS_HOST_DIR, "cg_input")

NOT_MACOS = "not macOS: cg_input posts CoreGraphics events"

# The bits under test, restated from input_flags.h. cg_input.c static-asserts
# the header against the system's own constants; this side is the third
# opinion, so a mask edited in the header does not quietly agree with itself.
CAPSLOCK = 0x00010000
SHIFT = 0x00020000
CONTROL = 0x00040000
OPTION = 0x00080000
COMMAND = 0x00100000
HELP = 0x00400000
FN = 0x00800000
DEVICE_LCONTROL = 0x00000001
DEVICE_LSHIFT = 0x00000002
DEVICE_RSHIFT = 0x00000004
DEVICE_LCOMMAND = 0x00000008
DEVICE_RCOMMAND = 0x00000010
DEVICE_LOPTION = 0x00000020
DEVICE_ROPTION = 0x00000040
DEVICE_CAPSLOCK = 0x00000080
DEVICE_RCONTROL = 0x00002000

MANAGED = (CAPSLOCK | SHIFT | CONTROL | OPTION | COMMAND | HELP | FN
           | DEVICE_LCONTROL | DEVICE_LSHIFT | DEVICE_RSHIFT | DEVICE_LCOMMAND
           | DEVICE_RCOMMAND | DEVICE_LOPTION | DEVICE_ROPTION
           | DEVICE_CAPSLOCK | DEVICE_RCONTROL)

# Not a modifier: it tells the window server not to merge this mouse move into
# the next one, and the sustained hover this client needs depends on it.
NON_COALESCED = 0x00000100

# The macOS virtual keycodes the host maps its modifiers to, and the one letter
# key the issue is about.
VK_CONTROL = 0x3B
VK_SHIFT = 0x38
VK_Q = 0x0C

# The harness that exercises the composition rule with no CoreGraphics in
# sight. It speaks a line protocol so the cases below read like the commands
# cg_input itself is given.
HARNESS = r"""
#include <stdio.h>
#include <string.h>
#include "input_flags.h"

int main(void) {
    char line[256], cmd[32];
    unsigned long long a = 0, b = 0;
    while (fgets(line, sizeof(line), stdin)) {
        if (sscanf(line, "%31s %llx %llx", cmd, &a, &b) < 1) continue;
        if (strcmp(cmd, "compose") == 0) {
            unsigned long long c = 0;
            sscanf(line, "%31s %llx %llx %llx", cmd, &a, &b, &c);
            printf("0x%llx\n", (unsigned long long)cgi_compose(a, b, c));
        } else if (strcmp(cmd, "hold") == 0) {
            unsigned int key = 0, down = 0;
            sscanf(line, "%31s %llx %x %u", cmd, &a, &key, &down);
            printf("0x%llx\n", (unsigned long long)cgi_hold(a, (uint16_t)key, (int)down));
        } else if (strcmp(cmd, "managed") == 0) {
            printf("0x%llx\n", (unsigned long long)CGI_MANAGED_MODIFIERS);
        } else {
            printf("err\n");
        }
        fflush(stdout);
    }
    return 0;
}
"""


def _build(directory, source_name, source_text, output_name, extra_args=()):
    """Compile `source_text` in `directory` and answer the binary's path."""
    source = os.path.join(directory, source_name)
    with open(source, "w") as handle:
        handle.write(source_text)
    binary = os.path.join(directory, output_name)
    subprocess.run(
        [os.environ.get("CC", "cc"), "-O0", "-Wall", "-Werror",
         "-I", CG_INPUT_DIR, "-o", binary, source, *extra_args],
        check=True, capture_output=True)
    return binary


def _drive(binary, commands, args=()):
    """Feed `commands` to `binary` one per line and answer its stdout lines."""
    result = subprocess.run(
        [binary, *args], input="".join(c + "\n" for c in commands),
        capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError("%s exited %d: %s"
                             % (binary, result.returncode, result.stderr))
    return result.stdout.splitlines()


class TheCompositionRuleTest(unittest.TestCase):
    """`input_flags.h`, compiled and executed rather than read.

    This half runs everywhere, including the Linux runner CI uses, because the
    header deliberately depends on nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = _build(cls.directory.name, "harness.c", HARNESS, "harness")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def compose(self, born, intrinsic, held):
        return int(_drive(
            self.binary,
            ["compose %x %x %x" % (born, intrinsic, held)])[0], 16)

    def hold(self, held, key, down):
        return int(_drive(self.binary,
                          ["hold %x %x %d" % (held, key, down)])[0], 16)

    def test_the_masks_here_are_the_masks_there(self):
        managed = int(_drive(self.binary, ["managed"])[0], 16)
        self.assertEqual(managed, MANAGED)
        self.assertEqual(managed & NON_COALESCED, 0)

    def test_a_session_modifier_that_is_neither_ours_nor_the_key_s(self):
        """The whole of #240: the Fn the session reports belongs to whichever
        key asserted it, and not to this event."""
        self.assertEqual(self.compose(FN, 0, 0), 0)
        self.assertEqual(self.compose(FN | CONTROL | DEVICE_LCONTROL, 0, 0), 0)

    def test_a_modifier_we_are_holding_is_put_on(self):
        """And the whole of what a blanket clear would have broken."""
        held = CONTROL | DEVICE_LCONTROL
        self.assertEqual(self.compose(0, 0, held), held)
        self.assertEqual(self.compose(FN, 0, held), held)

    def test_the_key_s_own_flags_survive(self):
        """F1 carries Fn because it is F1, not because the session said so --
        so stripping it could stop F1 registering as F1."""
        self.assertEqual(self.compose(FN, FN, 0), FN)
        self.assertEqual(self.compose(0, FN, 0), FN)

    def test_the_key_s_own_flags_and_ours_are_both_carried(self):
        """Ctrl+F1: one from the chord we are holding, one from the key."""
        held = CONTROL | DEVICE_LCONTROL
        self.assertEqual(self.compose(FN, FN, held), FN | held)

    def test_the_session_cannot_add_a_modifier_the_key_does_not_carry(self):
        """The same session Fn, on the key next to F1, is still dropped."""
        self.assertEqual(self.compose(FN, 0, 0), 0)

    def test_bits_that_are_not_modifiers_survive(self):
        self.assertEqual(self.compose(NON_COALESCED | FN, 0, 0), NON_COALESCED)

    def test_control_then_shift_is_the_unlock_chord(self):
        held = self.hold(0, VK_CONTROL, 1)
        held = self.hold(held, VK_SHIFT, 1)
        self.assertEqual(
            held, CONTROL | DEVICE_LCONTROL | SHIFT | DEVICE_LSHIFT)

    def test_a_release_takes_the_modifier_back_off(self):
        held = self.hold(0, VK_CONTROL, 1)
        self.assertEqual(self.hold(held, VK_CONTROL, 0), 0)

    def test_an_ordinary_key_holds_nothing(self):
        self.assertEqual(self.hold(0, VK_Q, 1), 0)
        held = CONTROL | DEVICE_LCONTROL
        self.assertEqual(self.hold(held, VK_Q, 1), held)
        self.assertEqual(self.hold(held, VK_Q, 0), held)

    def test_caps_lock_is_cleared_but_never_held(self):
        """It latches rather than being held, so pressing it holds nothing --
        and a session that has it on cannot capitalise what the bot types."""
        self.assertEqual(self.hold(0, 0x39, 1), 0)
        self.assertEqual(self.compose(CAPSLOCK | DEVICE_CAPSLOCK, 0, 0), 0)


@unittest.skipUnless(sys.platform == "darwin", NOT_MACOS)
class TheBinaryStampsEveryEventItPostsTest(unittest.TestCase):
    """The real `cg_input`, built and driven, posting nothing.

    A composition rule that is right and not reached at one of the six post
    sites is the bug still shipping, so these cases go through the program
    rather than the header.
    """

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        with open(os.path.join(CG_INPUT_DIR, "cg_input.c")) as handle:
            source = handle.read()
        cls.binary = _build(cls.directory.name, "cg_input.c", source, "cg_input",
                            extra_args=("-framework", "ApplicationServices"))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def posts(self, commands):
        """Every `post` line, as (kind, code, born, intrinsic, flags)."""
        lines = _drive(self.binary, commands, args=("--dry-run",))
        posted = []
        for line in lines:
            match = re.match(
                r"post (\S+) (-?\d+) born=0x([0-9a-f]+) intrinsic=0x([0-9a-f]+)"
                r" flags=0x([0-9a-f]+)$", line)
            if match:
                posted.append((match.group(1), int(match.group(2)),
                               int(match.group(3), 16), int(match.group(4), 16),
                               int(match.group(5), 16)))
        self.assertEqual(lines.count("ok"), len(commands),
                         "every command should still answer ok")
        return posted

    def assertCarries(self, posted, held):
        """`posted` carries what we hold and what each key carries of its own,
        and nothing else the session had put on it.

        Deterministic whatever the session happens to hold, which is what makes
        it worth asserting at all -- and on a machine whose session carries a
        stray modifier it is also the live defect report, since `born` shows it
        and `flags` must not.
        """
        for kind, code, born, intrinsic, flags in posted:
            expected = (intrinsic & MANAGED) | held
            self.assertEqual(
                flags & MANAGED, expected,
                "%s %d: expected 0x%x, got 0x%x (born 0x%x, intrinsic 0x%x)"
                % (kind, code, expected, flags & MANAGED, born, intrinsic))
            self.assertEqual(
                flags & ~MANAGED, born & ~MANAGED,
                "%s %d changed a bit that is not a modifier" % (kind, code))

    def assertKeyCarriesOfItsOwn(self, posted, intrinsic):
        """What the key itself contributes, so the contract above is not
        vacuous -- an `intrinsic` of 0 everywhere would satisfy it trivially."""
        for kind, code, _, actual, _ in posted:
            self.assertEqual(
                actual & MANAGED, intrinsic,
                "%s %d carries 0x%x of its own, expected 0x%x"
                % (kind, code, actual & MANAGED, intrinsic))

    def test_the_twin_the_key_s_own_flags_come_from_is_a_private_one(self):
        """Read out of the source, which the rest of this file avoids -- and
        here it is the only way.

        A twin made with a NULL source carries the key's own flags *and* the
        session's, so it differs from the private one only while the session is
        dirty. On a clean session the two are identical, so no assertion over
        what the binary reports can tell them apart, and the one thing that
        distinguishes them is which source it asked.
        """
        with open(os.path.join(CG_INPUT_DIR, "cg_input.c")) as handle:
            source = handle.read()
        self.assertIn("CGEventSourceCreate(kCGEventSourceStatePrivate)", source)
        self.assertIn(
            "CGEventCreateKeyboardEvent(intrinsicSource, key, down)", source,
            "the twin the intrinsic flags are read from must be the private "
            "one, or it inherits the session it exists to exclude")

    def test_every_command_that_posts_reports_a_post(self):
        """The six post sites, so a site that skips the stamp is visible as a
        missing line rather than as nothing at all."""
        posted = self.posts(["move 10 10", "down 0", "up 0", "drag 20 20 0",
                             "doubleclick 0", "keydown 12", "keyup 12",
                             "text hi", "scroll 0 3"])
        kinds = [kind for kind, _, _, _, _ in posted]
        self.assertEqual(kinds.count("mouse"), 8)   # move, down, up, drag, 4x
        self.assertEqual(kinds.count("key"), 1)
        self.assertEqual(kinds.count("keyup"), 1)
        self.assertEqual(kinds.count("text"), 4)    # down and up for h and i
        self.assertEqual(kinds.count("scroll"), 1)

    def test_a_letter_key_is_posted_as_a_letter(self):
        """`Q` with no modifier of ours is `Q`, whatever the session reports.

        This is the case the issue is named for: with the session's Fn on the
        event, `Q` is Quick Note, `E` the emoji picker, `C` Control Centre and
        `F` toggle-full-screen.
        """
        self.assertCarries(self.posts(["keydown 12", "keyup 12"]), 0)

    def test_a_click_carries_nothing_of_its_own(self):
        """The intrinsic term is what the *key* carries, so a mouse event's is
        zero -- a private-source mouse event reads 0x0, measured.

        Without this the contract above is satisfiable by a site that reports
        its own born flags as intrinsic, which is the leak wearing the fix's
        clothes: every assertion still passes and the session rides out on
        every click.
        """
        posted = self.posts(["move 10 10", "down 0", "up 0", "drag 20 20 0",
                             "doubleclick 0", "scroll 0 3", "text z"])
        self.assertKeyCarriesOfItsOwn(posted, 0)
        self.assertCarries(posted, 0)

    def test_a_click_under_a_held_modifier_still_carries_nothing_of_its_own(self):
        """The same, with Control held, so the case cannot pass by the session
        happening to be clean."""
        posted = self.posts(["keydown 59", "down 0", "up 0"])
        self.assertKeyCarriesOfItsOwn(posted[1:], 0)
        self.assertCarries(posted[1:], CONTROL | DEVICE_LCONTROL)

    def test_a_weapon_hotkey_keeps_the_fn_that_makes_it_a_weapon_hotkey(self):
        """F1-F4 are the bot's weapon slots, and macOS marks them Fn keys.

        That bit is the key's own and not the session's -- measured on a
        session reporting no Fn at all, where a private-source F1 still reads
        0x20800000 while a private-source Q reads 0x20000000. Stripping it is
        what "set the flags to the modifiers the bot is holding" would have
        done, and it could stop F1 registering as F1.
        """
        posted = self.posts(["keydown 122", "keyup 122"])
        self.assertKeyCarriesOfItsOwn(posted, FN)
        self.assertCarries(posted, 0)

    def test_the_arrows_keep_their_own_two_bits(self):
        """The navigation block is marked the same way, with the numeric-pad
        bit besides -- which is outside the managed mask and so survives by a
        different route."""
        posted = self.posts(["keydown 123"])
        self.assertKeyCarriesOfItsOwn(posted, FN)
        self.assertCarries(posted, 0)

    def test_a_weapon_hotkey_under_a_held_modifier_carries_both(self):
        """`Alt+F1` toggles the propulsion module and `F1` fires a gun, so the
        two have to stay distinguishable while Fn rides on both."""
        posted = self.posts(["keydown 59", "keydown 122"])
        self.assertCarries(posted[1:], CONTROL | DEVICE_LCONTROL)
        self.assertKeyCarriesOfItsOwn(posted[1:], FN)

    def test_the_key_that_asserted_fn_does_not_pass_it_on(self):
        """The leak, in the shape the client produces it: the bot's own F1 puts
        Fn into the session, and the `Q` after it must not pick it up."""
        posted = self.posts(["keydown 122", "keyup 122", "keydown 12"])
        self.assertKeyCarriesOfItsOwn(posted[:2], FN)
        self.assertKeyCarriesOfItsOwn(posted[2:], 0)
        self.assertCarries(posted, 0)

    def test_ctrl_click_is_still_a_ctrl_click(self):
        """How the bot locks a target, and what a blanket clear would break."""
        posted = self.posts(["keydown 59", "move 10 10", "down 0", "up 0"])
        self.assertCarries(posted[:1], CONTROL | DEVICE_LCONTROL)
        self.assertCarries(posted[1:], CONTROL | DEVICE_LCONTROL)

    def test_ctrl_shift_click_is_still_a_ctrl_shift_click(self):
        """How it unlocks one."""
        posted = self.posts(["keydown 59", "keydown 56", "down 0", "up 0"])
        self.assertCarries(
            posted[2:], CONTROL | DEVICE_LCONTROL | SHIFT | DEVICE_LSHIFT)

    def test_a_click_after_the_release_is_a_plain_click(self):
        """A Control left on a click is a secondary click: a context menu where
        the bot meant to select."""
        posted = self.posts(["keydown 59", "down 0", "up 0", "keyup 59",
                             "move 10 10", "down 0", "up 0"])
        self.assertCarries(posted[-3:], 0)

    def test_the_modifier_keyup_no_longer_carries_the_modifier(self):
        """What the same release does in hardware."""
        posted = self.posts(["keydown 59", "keyup 59"])
        self.assertCarries(posted[:1], CONTROL | DEVICE_LCONTROL)
        self.assertCarries(posted[1:], 0)

    def test_typing_and_scrolling_are_stamped_too(self):
        posted = self.posts(["keydown 59", "text z", "scroll 0 3"])
        self.assertCarries(posted[1:], CONTROL | DEVICE_LCONTROL)

    def test_the_session_never_reaches_the_wire(self):
        """Nothing the session is holding survives unless we are holding it.

        This is the general form of every case above, and the one that reports
        the live defect: on a machine whose session carries a stray modifier,
        `born` shows it and `flags` must not.
        """
        posted = self.posts(["move 10 10", "down 0", "up 0", "keydown 12",
                             "keyup 12", "text z", "scroll 0 3"])
        self.assertCarries(posted, 0)


if __name__ == "__main__":
    unittest.main()
