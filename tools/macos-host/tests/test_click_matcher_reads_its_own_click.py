"""The matcher that answers "did we click here" reads the click the bot issues.

`findMouseButtonClickLocationsInListOfEffects` folds over the previous step's
effects and returns the points a mouse button went down at. Everything that asks
"did I already click that" reads it: the module-button settling guard
(`clickModuleButtonButWaitIfClickedInPreviousStep`, through
`doEffectsClickModuleButton`) and the cascade's own
`discardContextMenuIfTooDistantFromTargetElement`.

**A click is not one effect, and the two host interfaces spell it differently.**
`effectsMouseClickAtLocation` is what every click in these bots is built from,
and on the Photon-era interface it emits

    [ MouseMoveTo location, ButtonDown button, ButtonUp button ]

while on the 2023 interface -- whose `EffectOnWindowStructure` has no
`ButtonDown` constructor at all -- it emits

    [ MouseMoveTo location, KeyDown (virtualKeyCodeFromMouseButton button), KeyUp ... ]

Issue #239: `eve-online-combat-anomaly-bot` and `eve-online-warp-to-0-autopilot`
carry the first encoding and a fold that matched only `MouseMoveTo` and
`KeyDown`, so the function returned the empty list for every click those two
bots have ever issued and every guard reading it answered "no" every time. The
mission runner and saxrat have had the `ButtonDown` arm since the same defect
was found and repaired there; saxrat's own doc comment records the diagnosis in
the past tense.

**The issue names four apps and the corpus said two**, and the two it was
wrong about were the two on the older interface. `eve-online-wingus` declared no
`ButtonDown` at all, so its click really was `KeyDown`-encoded, the arm it had
was the right one, and an arm naming `ButtonDown` would not have compiled;
`eve-online-mining-bot` was in the same position until its whole tree was
replaced with Viir's current upstream, on the 2024_10_19 interface, and it now
carries `ButtonDown` like the rest of `PHOTON_APPS`. Wingus has since been
retired with that interface (`notes/retire-wingus.md`), so **no app in the repo
spells a click the second way today** -- which is exactly why the correction is
kept as a rule rather than as a list.
`test_the_arm_matches_the_encoding_the_app_actually_emits` derives what arm an
app needs from that app's own `effectsMouseClickAtLocation`, so a later port
cannot copy the fix into an app whose clients spell a click the other way, and
it says so about an app that arrives after this file was written.

The strongest case here is the one that needs no knowledge of either encoding:
**every app's matcher is asked about that app's own `effectsMouseClickAtLocation`
output**, through the real compiler. That is the case the two fixed apps failed
before this change and the case that goes red if either arm is removed from any
of them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS_DIR = os.path.join(REPO, "implement", "applications", "eve-online")

# The dialects, named by what their effect type is called. Every app in a group
# vendors the same `Common/EffectOnWindow.elm` vocabulary.
#
# eve-online-mining-bot moved from the older group to PHOTON_APPS when its
# whole tree was replaced with Viir's current upstream (a materially newer
# generation on the 2024_10_19 host interface) -- its Common/EffectOnWindow.elm
# now carries ButtonDown and effectsMouseClickAtLocation builds the
# [ MouseMoveTo, ButtonDown, ButtonUp ] shape like every other Photon-era app.
#
# `eve-online-wingus` was the last app in the KeyDown-encoded group and left
# with the 2023 host interface (see `notes/retire-wingus.md`), so that group is
# empty and is not written out. `DIALECTS` is kept as a list of groups rather
# than collapsed to one, because a second encoding arriving is what this file
# exists to keep straight -- and the rule that decides which arm an app needs,
# `test_the_arm_matches_the_encoding_the_app_actually_emits`, derives the answer
# from each app's own source rather than from this list, so it goes on working
# for an app nobody has grouped yet.
PHOTON_APPS = (
    "eve-online-mission-runner",
    "eve-online-saxrat",
    "eve-online-combat-anomaly-bot",
    "eve-online-warp-to-0-autopilot",
    "eve-online-mining-bot",
)
DIALECTS = (PHOTON_APPS,)
ALL_APPS = tuple(app for group in DIALECTS for app in group)

MATCHER = "findMouseButtonClickLocationsInListOfEffects"

PREAMBLE = (
    "import EveOnline.BotFramework as BF",
    "import Common.EffectOnWindow as EW",
)

# One point the click is aimed at, one somewhere else, and a virtual key that is
# not a mouse button (`0x41` is A).
DEFINITIONS = (
    "clickAt = { x = 137, y = 421 }",
    "otherAt = { x = 512, y = 33 }",
    "leftCode = EW.virtualKeyCodeFromMouseButton EW.MouseButtonLeft",
    "letterA = EW.VirtualKeyCodeFromInt 0x41",
)

# Asked of every app, in this order. Each is a `Bool`.
QUESTIONS = {
    "its own left click is seen":
        "BF.%s EW.MouseButtonLeft"
        " (EW.effectsMouseClickAtLocation EW.MouseButtonLeft clickAt)"
        " == [ clickAt ]" % MATCHER,
    "a right click is not a left one":
        "BF.%s EW.MouseButtonLeft"
        " (EW.effectsMouseClickAtLocation EW.MouseButtonRight clickAt)"
        " == []" % MATCHER,
    "its own right click is seen":
        "BF.%s EW.MouseButtonRight"
        " (EW.effectsMouseClickAtLocation EW.MouseButtonRight clickAt)"
        " == [ clickAt ]" % MATCHER,
    "two clicks come back in the order they were issued":
        "BF.%s EW.MouseButtonLeft"
        " (EW.effectsMouseClickAtLocation EW.MouseButtonLeft clickAt"
        " ++ EW.effectsMouseClickAtLocation EW.MouseButtonLeft otherAt)"
        " == [ clickAt, otherAt ]" % MATCHER,
    "a press with no move before it records nothing":
        "BF.%s EW.MouseButtonLeft"
        " (List.drop 1 (EW.effectsMouseClickAtLocation EW.MouseButtonLeft clickAt))"
        " == []" % MATCHER,
    "a button spelled as a virtual key is still read":
        "BF.%s EW.MouseButtonLeft"
        " [ EW.MouseMoveTo clickAt, EW.KeyDown leftCode, EW.KeyUp leftCode ]"
        " == [ clickAt ]" % MATCHER,
    "a keystroke that is not a mouse button records nothing":
        "BF.%s EW.MouseButtonLeft"
        " [ EW.MouseMoveTo clickAt, EW.KeyDown letterA, EW.KeyUp letterA ]"
        " == []" % MATCHER,
}


def app_source(app, *parts):
    with open(os.path.join(APPS_DIR, app, *parts), encoding="utf-8") as source:
        return source.read()


def declaration(text, name):
    """The top-level declaration `name`, from its type annotation to its end.

    Sliced to the next blank-line-blank-line boundary rather than searched for a
    substring: what several cases here assert is the *shape* of one arm, and a
    substring found anywhere in a 2,000-line module says nothing about which
    declaration holds it.
    """
    start = text.index("\n%s :" % name) + 1
    return text[start:text.index("\n\n\n", start)]


def carries_button_down(app):
    """Whether this app's effect vocabulary has a `ButtonDown` constructor."""
    return bool(re.search(
        r"^\s+\|\s+ButtonDown MouseButton$",
        app_source(app, "Common", "EffectOnWindow.elm"), re.M))


class EveryAppReadsItsOwnClick(unittest.TestCase):
    """The real compiler, asked what each app's matcher does with each app's click.

    Nothing here knows which constructor an app uses. The effects are built by
    the app's own `effectsMouseClickAtLocation`, which is what every click in
    that bot is built from, so an app whose fold does not cover its own encoding
    fails whatever the encoding is.
    """

    @classmethod
    def setUpClass(cls):
        cls.repls = {}
        cls.answers = {}
        for app in ALL_APPS:
            repl = open_repl(ElmRepl, prefix="click-matcher-%s-" % app,
                             preamble=PREAMBLE,
                             app_dir=os.path.join(APPS_DIR, app))
            cls.repls[app] = repl
            cls.answers[app] = dict(zip(
                QUESTIONS,
                repl.evaluate(list(QUESTIONS.values()), DEFINITIONS)))

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def assert_every_app_answers(self, question):
        for app in ALL_APPS:
            with self.subTest(app=app):
                self.assertTrue(
                    self.answers[app][question],
                    "%s: %s -- %s"
                    % (app, question, QUESTIONS[question]))

    def test_a_click_the_bot_issues_is_a_click_the_matcher_reports(self):
        """#239 itself: this answered `[]` in the two apps missing the arm."""
        self.assert_every_app_answers("its own left click is seen")

    def test_the_button_asked_about_is_the_button_matched(self):
        self.assert_every_app_answers("a right click is not a left one")

    def test_the_right_button_is_read_too(self):
        """`discardContextMenuIfTooDistantFromTargetElement` asks about this one."""
        self.assert_every_app_answers("its own right click is seen")

    def test_each_click_in_a_sequence_is_reported_once_and_in_order(self):
        self.assert_every_app_answers(
            "two clicks come back in the order they were issued")

    def test_a_press_the_cursor_never_travelled_to_is_not_a_location(self):
        """The fold has no location to attribute, so it must report none.

        Reported as a *click at the last known position* it would be worse than
        no answer: the guards that read this ask whether a specific element was
        clicked.
        """
        self.assert_every_app_answers(
            "a press with no move before it records nothing")

    def test_the_virtual_key_spelling_is_still_read(self):
        """The `KeyDown` arm stays, in both dialects.

        #239 asks whether it is dead once `ButtonDown` is matched. It is not:
        it is the *only* encoding the 2023-interface apps have, and on the
        Photon-era apps keeping it costs nothing and is strictly more forgiving.
        This case is what goes red if it is removed from any of the six.
        """
        self.assert_every_app_answers(
            "a button spelled as a virtual key is still read")

    def test_an_ordinary_keystroke_is_not_a_click(self):
        self.assert_every_app_answers(
            "a keystroke that is not a mouse button records nothing")


class TheArmMatchesTheEncoding(unittest.TestCase):
    """Which arm an app needs is decided by what its own click emits.

    Read out of the source rather than executed, because the point is the
    relation between two files: an app that grows or loses the `ButtonDown`
    constructor has to move its fold with it, and the executed cases above can
    only say that today's pair agree.
    """

    def matcher(self, app):
        return declaration(
            app_source(app, "EveOnline", "BotFramework.elm"), MATCHER)

    def test_the_arm_matches_the_encoding_the_app_actually_emits(self):
        for app in ALL_APPS:
            with self.subTest(app=app):
                emits_button_down = "ButtonDown mouseButton" in declaration(
                    app_source(app, "Common", "EffectOnWindow.elm"),
                    "effectsMouseClickAtLocation")
                self.assertEqual(
                    emits_button_down, carries_button_down(app),
                    "an app builds its click from the constructors it has")
                self.assertEqual(
                    emits_button_down,
                    "ButtonDown button ->" in self.matcher(app),
                    "the fold has an arm for the constructor the click uses")

    def test_every_photon_era_app_carries_the_constructor_and_the_arm(self):
        for app in PHOTON_APPS:
            with self.subTest(app=app):
                self.assertTrue(carries_button_down(app))
                self.assertIn("ButtonDown button ->", self.matcher(app))
                self.assertIn("KeyDown keyDown ->", self.matcher(app))

    def test_the_copies_within_a_dialect_are_identical(self):
        """Nothing in this function is app-specific, so a divergence is a bug.

        #239 is what four copies drifting from two cost: the repair landed in
        the two apps where it hurt and the other four kept the defect for as
        long as nobody compared them.
        """
        for group in DIALECTS:
            bodies = {app: self.matcher(app) for app in group}
            reference = bodies[group[0]]
            for app, body in bodies.items():
                with self.subTest(app=app):
                    self.assertEqual(body, reference)


class TheGuardsThatReadIt(unittest.TestCase):
    """What the two repaired apps now have that they did not, in source.

    Both guards compiled and ran throughout; what they could not do is see a
    click. These cases pin that they still read the matcher, so a later change
    that quietly stops consulting it is a change somebody has to argue for.
    """

    REPAIRED = ("eve-online-combat-anomaly-bot", "eve-online-warp-to-0-autopilot")

    def separating_memory(self, app):
        return app_source(app, "EveOnline", "BotFrameworkSeparatingMemory.elm")

    def test_the_module_button_settling_guard_still_reads_the_matcher(self):
        for app in self.REPAIRED:
            with self.subTest(app=app):
                guard = declaration(
                    self.separating_memory(app),
                    "clickModuleButtonButWaitIfClickedInPreviousStep")
                self.assertIn("moduleButtonClickSettlingSteps", guard)
                self.assertIn("doEffectsClickModuleButton moduleButton", guard)
                self.assertIn(
                    MATCHER,
                    declaration(
                        app_source(app, "EveOnline", "BotFramework.elm"),
                        "doEffectsClickModuleButton"))

    def test_the_cascade_still_projects_the_click_it_actually_made(self):
        for app in self.REPAIRED:
            with self.subTest(app=app):
                self.assertIn(
                    MATCHER,
                    declaration(
                        self.separating_memory(app),
                        "discardContextMenuIfTooDistantFromTargetElement"))


if __name__ == "__main__":
    unittest.main()
