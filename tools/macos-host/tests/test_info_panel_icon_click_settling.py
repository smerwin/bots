"""Tests for the settling guard on the info panel's enable-icon click.

Issue #227. `ensureInfoPanelLocationInfoIsExpanded` clicks the info panel's own
toggle icon whenever the panel does not parse out of a reading, and that click
carried **no settling guard**: a bare `decideActionForCurrentStep clickEffect`,
fired once per reading for as long as the panel stayed absent. Because the icon
is a toggle, roughly every second click in a stretch like that turns the panel
back off -- mission_run22 holds a stretch of 184 consecutive readings.

The fix is the pattern the module buttons already have --
`clickModuleButtonButWaitIfClickedInPreviousStep` and
`moduleButtonClickSettlingSteps` -- generalized from a `ShipUIModuleButton` to
any `UIElement` (`doEffectsClickUIElement`, mirroring
`EveOnline.BotFramework.doEffectsClickModuleButton`), because the icon is not a
module button and the settling logic needs the previous steps' own effects,
which the function did not receive before this change.

**What this guarantees, and what it does not.** The issue's own open question is
genuinely open: nobody knows whether the click enables the panel and the next
one undoes it, or whether the click never enables it at all -- a reading records
only the panel's *absence*, never its state. This change does not answer that.
What it guarantees is narrower and does not depend on the answer: the icon is
never clicked again while an earlier click on it is still within its settling
window, so the toggle-back mechanism the issue names cannot fire from this
branch. Deliberately not added: a bound or a give-up on the branch -- one click
that lands ought to be enough, and if it demonstrably is not, that is a separate
finding.

**#297 was that finding, and two things in here moved with it.** It demonstrably
was not enough: the branch next door -- "the panel is in the tree but drawn
collapsed" -- had no guard at all, the two alternated because each one's click
produces the other's precondition, and the pair held the whole decision tree
below `generalSetupInUserInterface` for 364 readings of one recorded run. So the
settling window is now read once for the declaration and keyed on
`infoPanelContainer`, which both branches' clicks land inside, rather than per
branch on an element that is missing from the tree on the reading the other
branch clicks; and while a click is settling the declaration answers `Nothing`
rather than `waitForProgressInGame`, so it stands aside instead of holding the
tree. The cases below that used to assert the wait now assert the stand-aside,
and the step-count wording ("I clicked this icon 3 step(s) ago") is gone from
the log with the branch that printed it. `test_info_panel_repair_deadlock.py`
carries that change's own reasoning and its fold over the alternation.

**The change lands in `EveOnline/BotFrameworkSeparatingMemory.elm` in five of
the six vendored copies** (`eve-online-mining-bot` is the exception -- see
below), and those five are not one file with five names -- they have already
diverged into three shapes, and the fix is written once per shape rather than
pasted five times:

  - `eve-online-mission-runner` and `eve-online-saxrat` (byte-identical before
    this change) carry `previousStepsEffects : List (List EffectOnWindowStruct)`
    on `StepDecisionContext` and already have `moduleButtonClickSettlingSteps` /
    `doEffectsClickModuleButton`, so the fix is the identical settling logic,
    generalized to `doEffectsClickUIElement`.
  - `eve-online-combat-anomaly-bot` and `eve-online-warp-to-0-autopilot` carry
    the same `previousStepsEffects` shape and the same settling machinery, on an
    older revision of this function's "icon missing" branch (left untouched).
  - `eve-online-wingus` is on the 2023 host interface, carries only
    `previousStepEffects : List EffectOnWindowStructure` (one step, not
    several) and has never had the module-button settling pattern ported into
    this file at all. The fix there is `doEffectsClickUIElement` asked
    directly as a `Bool` against that one step, which is the same rule with
    one step of history instead of five -- all this shape's
    `StepDecisionContext` carries.

`eve-online-mining-bot` was on this same 2023-interface shape until its whole
tree was replaced with Viir's current upstream (2024_10_19 interface, a
materially newer generation) -- that tree carries none of #227/#297 at all,
not even the older single-step form: `ensureInfoPanelLocationInfoIsExpanded`
there takes only a reading, with no settling guard of any kind ahead of its
click. `eve-online-mining-bot` is therefore excluded from every case in this
file rather than assigned to a shape, and porting #227/#297 into the newer
base is tracked as follow-up work, not done here.

Confirmed by mutation: reverting the mission runner's guard to the pre-fix
`case mouseClickOnUIElement ... of Err _ -> ... Ok clickEffect ->
decideActionForCurrentStep clickEffect` (no settling check at all) makes
`TheIconWaitsAfterItsOwnClick` fail -- the icon is clicked again on the very
next reading instead of waiting, which is exactly the toggle-back this change
exists to stop. Also confirmed failing: moving the boundary in
`TheSettlingWindowIsFiveSteps` by one in either direction.

**Executed rather than restated.** The settling guard and the reading it is
asked about both go through the real `Bot.elm` in `elm repl`, with the reading
built from a UI tree run through the real `EveOnline.ParseUserInterface` --
`InfoPanelContainer` -> `iconCont` -> a `LocationInfo.png`-textured sprite, and
deliberately no `InfoPanelLocationInfo` node, so the panel reads absent and the
icon-click branch is the one reached. The wiring -- that `previousStepsEffects`
actually reaches the function from `generalSetupInUserInterface` -- is read out
of the source instead, since it is not an expression.

**Since fixed.** Two of the six vendored copies --
`eve-online-combat-anomaly-bot` and `eve-online-warp-to-0-autopilot` -- carried
a *separate, pre-existing* defect in their own vendored
`EveOnline/BotFramework.elm`: `findMouseButtonClickLocationsInListOfEffects`
there recognized only the older `KeyDown`-encoded click, never the
`ButtonDown`/`ButtonUp` pair `effectsMouseClickAtLocation` actually emits in
their host interface. That function is what both the pre-existing
`doEffectsClickModuleButton` and this change's `doEffectsClickUIElement` are
built on, so in those two apps *neither* guard could recognize a click that had
just been dispatched. Issue #239 took that up and the arm is now present in
every app whose interface has the constructor, so both guards settle there too.
The claim this file used to record as a case now lives in
`test_click_matcher_reads_its_own_click.py`, which pins the arm and the
encoding it matches across all six apps.

Also unverified: whether the click lands on the live client at all, and whether
a landed click enables the panel or a second one undoes it -- see the issue's
own "Unverified" section, unchanged by this PR. No run has been flown since.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, PREAMBLE, SAXRAT_DIR, SaxratRepl, body_of, collapsed,
    node, source_of, tree_with)

COMBAT_ANOMALY_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-combat-anomaly-bot")
WARP_TO_0_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-warp-to-0-autopilot")
WINGUS_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingus")

SIX_VENDORED_FRAMEWORKS = {
    "mission runner": os.path.join(
        MISSION_RUNNER_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm"),
    "saxrat": os.path.join(
        SAXRAT_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm"),
    "combat anomaly bot": os.path.join(
        COMBAT_ANOMALY_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm"),
    "warp-to-0 autopilot": os.path.join(
        WARP_TO_0_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm"),
    "wingus": os.path.join(
        WINGUS_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm"),
}

def info_panel_container(icon_region):
    """An `InfoPanelContainer` with the location-info icon and no panel.

    No `InfoPanelLocationInfo` node, so `.infoPanelLocationInfo` reads
    `Nothing` and `ensureInfoPanelLocationInfoIsExpanded` reaches the branch
    this file is about. The icon is found by `parseInfoPanelIconsFromInfoPanelContainer`
    two ways: a descendant named `iconCont`, then within it a descendant whose
    `texturePath` ends with `LocationInfo.png`.
    """
    icon_cont = node("Container", {"_name": "iconCont"}, [
        node("Sprite", {"texturePath": "res:/UI/Texture/Icons/74_16_190.png"
                                        "/LocationInfo.png"}, region=icon_region),
    ], region=(0, 0, 90, 20))
    return node("InfoPanelContainer", {}, [icon_cont], region=(0, 0, 200, 100))


EXTRA_PREAMBLE = PREAMBLE + (
    "import EveOnline.BotFrameworkSeparatingMemory",
    "import Common.DecisionPath",
)


class IconSettlingRepl(ElmRepl):
    """The mission runner's own `Bot.elm`, plus what this file needs asked."""

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", EXTRA_PREAMBLE)
        super().__init__(**kwargs)

    HELPERS = [
        SaxratRepl.reading_binding(
            "reading", [info_panel_container((10, 5, 20, 16))]),
        "icon = reading |> Maybe.andThen"
        " (.infoPanelContainer >> Maybe.andThen .icons >> Maybe.andThen .locationInfo)",
        "clickPoint icn = EveOnline.ParseUserInterface.centerFromDisplayRegion"
        " icn.totalDisplayRegionVisible",
        "clickEffects = icon |> Maybe.map"
        " (clickPoint >> EffectOnWindow.effectsMouseClickAtLocation"
        " EffectOnWindow.MouseButtonLeft) |> Maybe.withDefault []",
        # Both apps' `ensureInfoPanelLocationInfoIsExpanded` takes
        # `List (List EffectOnWindowStruct)` here, most-recent-step-first --
        # the same convention `clickModuleButtonButWaitIfClickedInPreviousStep`
        # already uses.
        "resultText steps = reading"
        " |> Maybe.andThen (EveOnline.BotFrameworkSeparatingMemory"
        ".ensureInfoPanelLocationInfoIsExpanded steps)"
        " |> Maybe.map (Common.DecisionPath"
        ".unpackToDecisionStagesDescriptionsAndLeaf >> Tuple.first"
        " >> String.join \" | \")"
        " |> Maybe.withDefault \"NOTHING\"",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class SaxratIconSettlingRepl(IconSettlingRepl, SaxratRepl):
    """The same bindings, pointed at saxrat.

    `IconSettlingRepl` first in the MRO: its `preamble` default (which adds
    `EveOnline.BotFrameworkSeparatingMemory` and `Common.DecisionPath` on top
    of `SaxratRepl`'s own) has to claim the `preamble` kwarg before
    `SaxratRepl.__init__` runs its own `setdefault` and wins by going first.
    """


class BothAppsRepl:
    """One repl per app, so every case below is asked of both."""

    @classmethod
    def setUpClass(cls):
        cls.repls = {"mission runner": open_repl(IconSettlingRepl),
                     "saxrat": open_repl(SaxratIconSettlingRepl)}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.strings(
                expressions, definitions=repl.with_helpers(definitions))

    def each_bool(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.evaluate(
                expressions, definitions=repl.with_helpers(definitions))


class TheIconIsPresentAndThePanelIsNot(BothAppsRepl, unittest.TestCase):
    """The fixture itself, before anything is concluded from it.

    A tree the parser silently makes nothing of would pass or fail every case
    below for reasons that have nothing to do with the guard.
    """

    def test_icon_reads_but_panel_does_not(self):
        for app, answers in self.each_bool([
                "icon /= Nothing",
                "reading |> Maybe.andThen .infoPanelContainer"
                " |> Maybe.andThen .infoPanelLocationInfo |> (==) Nothing",
                "clickEffects /= []",
        ]):
            self.assertEqual(
                answers, [True, True, True],
                "%s: fixture did not parse as intended" % app)


class TheIconClicksWhenNothingHasClickedItYet(BothAppsRepl, unittest.TestCase):
    def test_no_previous_click_means_click_now(self):
        for app, (answer,) in self.each(["resultText []"]):
            self.assertIn(
                "Click on the icon to enable the info panel.", answer,
                "%s: %s" % (app, answer))


class TheIconIsNotClickedAgainAfterItsOwnClick(
        BothAppsRepl, unittest.TestCase):
    """The whole point of this change.

    A click on the icon one reading ago must not be repeated -- repeating it is
    exactly the toggle-back mechanism issue #227 is about. Mutating the guard
    away (reverting to the pre-fix bare `decideActionForCurrentStep
    clickEffect`) makes this fail: the icon is clicked again immediately.

    **What the settling case answers changed with #297**, and these cases
    changed with it. It used to be `waitForProgressInGame` under a branch naming
    the step count; it is now `Nothing`, so the repair stands aside and the rest
    of the decision tree gets the reading. The reason is in
    `test_info_panel_repair_deadlock.py`: this declaration is reached from
    `generalSetupInUserInterface`, above the retreat, so a wait here is the
    retreat unreachable, and #227's own "deliberately not added: a bound or a
    give-up" is what #297 came back to overturn. The step count went with the
    branch -- a cost, and a real one for reading a log.
    """

    def test_one_step_ago_does_not_click_again(self):
        for app, (answer,) in self.each(["resultText [ clickEffects ]"]):
            self.assertEqual("NOTHING", answer, app)

    def test_two_steps_ago_does_not_click_again_either(self):
        for app, (answer,) in self.each(
                ["resultText [ [], clickEffects ]"]):
            self.assertEqual("NOTHING", answer, app)


class TheSettlingWindowIsFiveSteps(BothAppsRepl, unittest.TestCase):
    """`moduleButtonClickSettlingSteps`, reused rather than re-derived.

    Both sides of the boundary: a click five steps back is still inside
    `List.take moduleButtonClickSettlingSteps` and is stood aside for; one six
    steps back has aged out of the window, and the icon is clicked again.
    """

    def test_five_steps_ago_still_stands_aside(self):
        for app, (answer,) in self.each(
                ["resultText (List.repeat 4 [] ++ [ clickEffects ])"]):
            self.assertEqual("NOTHING", answer, app)

    def test_six_steps_ago_clicks_again(self):
        for app, (answer,) in self.each(
                ["resultText (List.repeat 5 [] ++ [ clickEffects ])"]):
            self.assertIn(
                "Click on the icon to enable the info panel.", answer, app)
            self.assertNotIn("step(s) ago", answer, app)


class GroupCRepl(ElmRepl):
    """The 2023-interface shape: one step of history, asked as a `Bool`."""

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", EXTRA_PREAMBLE)
        super().__init__(**kwargs)

    HELPERS = [
        SaxratRepl.reading_binding(
            "reading", [info_panel_container((10, 5, 20, 16))]),
        "icon = reading |> Maybe.andThen"
        " (.infoPanelContainer >> Maybe.andThen .icons >> Maybe.andThen .locationInfo)",
        "clickPoint icn = EveOnline.ParseUserInterface.centerFromDisplayRegion"
        " icn.totalDisplayRegionVisible",
        "clickEffects = icon |> Maybe.map"
        " (clickPoint >> EffectOnWindow.effectsMouseClickAtLocation"
        " EffectOnWindow.MouseButtonLeft) |> Maybe.withDefault []",
        # `ensureInfoPanelLocationInfoIsExpanded` here takes the one
        # previous step's effects directly, not a list of steps.
        "resultText step = reading"
        " |> Maybe.andThen (EveOnline.BotFrameworkSeparatingMemory"
        ".ensureInfoPanelLocationInfoIsExpanded step)"
        " |> Maybe.map (Common.DecisionPath"
        ".unpackToDecisionStagesDescriptionsAndLeaf >> Tuple.first"
        " >> String.join \" | \")"
        " |> Maybe.withDefault \"NOTHING\"",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class GroupCBothAppsRepl:
    @classmethod
    def setUpClass(cls):
        cls.repls = {
            "wingus": open_repl(GroupCRepl, app_dir=WINGUS_DIR),
        }

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.strings(
                expressions, definitions=repl.with_helpers(definitions))


class TheGuardHoldsOnTheOlderHostInterfaceToo(
        GroupCBothAppsRepl, unittest.TestCase):
    """`eve-online-wingus`.

    It has never had the module-button settling pattern in this file, and
    `StepDecisionContext` here carries only the immediately previous step's
    effects -- so the guard is the same rule with one step of history rather
    than five, which is all this shape has to give it. `eve-online-mining-bot`
    used to share this shape; its tree was replaced with Viir's current
    upstream and it no longer carries this file's settling-guard mechanism at
    all, in any shape -- see the exclusion note near `SIX_VENDORED_FRAMEWORKS`.
    """

    def test_no_previous_click_means_click_now(self):
        for app, (answer,) in self.each(["resultText []"]):
            self.assertIn(
                "Click on the icon to enable the info panel.", answer, app)

    def test_last_steps_click_is_not_repeated(self):
        for app, (answer,) in self.each(["resultText clickEffects"]):
            self.assertEqual("NOTHING", answer, app)


class NoClickIsReachableWithoutTheSharedGuardTest(unittest.TestCase):
    """The bug itself, restated for where the guard now lives.

    #227 put a settling check *inside* the branch that clicks, and this case
    used to refuse the shape that lacked it: `Just iconLocationInfoPanel ->`
    followed straight by a click. #297 moved the check above both branches,
    because the branch that has to notice a click is not the branch that made
    it -- so that literal shape is back in four of the copies and is no longer
    the thing to refuse.

    What is refused instead is the property both revisions were after: a click
    this declaration can reach without the settling guard having answered first.
    """

    def test_the_guard_comes_before_every_click_in_every_copy(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path),
                        "ensureInfoPanelLocationInfoIsExpanded"))
            guard = block.find("infoPanelRepairClickIsSettling")
            self.assertNotEqual(
                -1, guard,
                "%s: the declaration does not consult a settling guard at "
                "all, which is the state #227 was filed on" % app)
            click = block.find("decideActionForCurrentStep")
            self.assertNotEqual(-1, click, "%s: no click left to guard" % app)
            self.assertLess(
                guard, click,
                "%s: a click is reachable before the settling guard is "
                "asked" % app)


class EachCopyNamesItsOwnSettlingCheckTest(unittest.TestCase):
    """The settling guard's own block, per copy.

    Read through `body_of`'s type-annotation-to-blank-line-pair slice rather
    than searched for anywhere in the file, so a settling check that landed in
    the wrong function would not satisfy this. #297 moved the check out of
    `ensureInfoPanelLocationInfoIsExpanded` and into a declaration of its own,
    so that is the block asked here; that the rule then consults it is
    `NoClickIsReachableWithoutTheSharedGuardTest` above.
    """

    # Which marker each copy's guard is built from, keyed the same way as
    # `SIX_VENDORED_FRAMEWORKS`.
    EXPECTED_MARKER = {
        "mission runner": "doEffectsClickUIElement",
        "saxrat": "doEffectsClickUIElement",
        "combat anomaly bot": "doEffectsClickUIElement",
        "warp-to-0 autopilot": "doEffectsClickUIElement",
        "wingus": "doEffectsClickUIElement",
    }

    def test_each_block_names_its_guard(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path), "infoPanelRepairClickIsSettling"))
            self.assertIn(
                self.EXPECTED_MARKER[app], block,
                "%s: settling guard not found in its own function" % app)


class BotElmThreadsThePreviousStepsEffectsThroughTest(unittest.TestCase):
    """The caller side: `generalSetupInUserInterface` has to pass what it now
    takes on to `ensureInfoPanelLocationInfoIsExpanded`, in each app that
    calls it.
    """

    APPS = {
        "mission runner": os.path.join(MISSION_RUNNER_DIR, "Bot.elm"),
        "saxrat": os.path.join(SAXRAT_DIR, "Bot.elm"),
        "combat anomaly bot": os.path.join(COMBAT_ANOMALY_DIR, "Bot.elm"),
        "wingus": os.path.join(WINGUS_DIR, "Bot.elm"),
    }

    def test_generalSetupInUserInterface_calls_it_with_an_argument(self):
        # `warp-to-0-autopilot` never calls `ensureInfoPanelLocationInfoIsExpanded`
        # at all, so it is not in `APPS` -- there is no caller side to check.
        # Neither does `eve-online-mining-bot`: its tree was replaced with
        # Viir's current upstream, which has no settling-guard mechanism for
        # this function to call at all.
        for app, path in self.APPS.items():
            block = collapsed(body_of(source_of(path), "generalSetupInUserInterface"))
            self.assertIn(
                "ensureInfoPanelLocationInfoIsExpanded", block, app)
            self.assertNotRegex(
                block,
                r"ensureInfoPanelLocationInfoIsExpanded\s*\]",
                "%s: still calls it with no argument, as a bare list "
                "element" % app)


class TheClickDetectionPrimitiveIsFixedEverywhereTest(unittest.TestCase):
    """The settling guard in this file is only as good as what it is built on.

    `doEffectsClickUIElement` reads
    `findMouseButtonClickLocationsInListOfEffects`, so an app whose copy of
    that function cannot recognize its own click has a guard that falls
    through to "click" every reading however correct the guard itself is.
    `eve-online-combat-anomaly-bot` and `eve-online-warp-to-0-autopilot` were
    in exactly that state when this file was written; #239 fixed them.

    What the arm matches per interface dialect, and the four copies being
    identical, is `test_click_matcher_reads_its_own_click.py`'s subject. This
    case asserts only the part this file depends on: every app whose settling
    guard this file exercises can see a `ButtonDown`-encoded click.
    """

    FRAMEWORKS = {
        "combat anomaly bot": os.path.join(
            COMBAT_ANOMALY_DIR, "EveOnline", "BotFramework.elm"),
        "warp-to-0 autopilot": os.path.join(
            WARP_TO_0_DIR, "EveOnline", "BotFramework.elm"),
        "mission runner": os.path.join(
            MISSION_RUNNER_DIR, "EveOnline", "BotFramework.elm"),
        "saxrat": os.path.join(SAXRAT_DIR, "EveOnline", "BotFramework.elm"),
    }

    def test_every_app_recognizes_a_button_down_click(self):
        for app, path in self.FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path), "findMouseButtonClickLocationsInListOfEffects"))
            self.assertIn(
                "ButtonDown button ->", block,
                "%s's click-finder no longer reads the constructor its own "
                "clicks are built from, so this file's settling guard cannot "
                "recognize a click it just dispatched" % app)
