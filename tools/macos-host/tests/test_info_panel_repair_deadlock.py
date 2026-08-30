"""Tests for the info panel repair not deadlocking, and not starving the tree.

Issue #297. `ensureInfoPanelLocationInfoIsExpanded` has two repair branches --
"the panel is not in the tree, click the icon that toggles it on" and "the panel
is in the tree but drawn collapsed, click `(x + 8, y + 8)` to expand it" -- and
#227 gave a settling guard to the first and not to the second. The two then
alternated, because each branch's click produces the other's precondition: the
icon click puts a *collapsed* panel in the tree, which stops the first branch
matching and starts the second; the second's click takes the panel back out of
the tree, which stops the second matching and starts the first.

**A second guard, one per branch, would not have fixed it.** That is the part
worth pinning, and the reason this file exists rather than a fifth case in
`test_info_panel_icon_click_settling.py`: on the reading where one branch runs,
the *other* branch's element is not in the tree at all, so a guard keyed on that
element has nothing to be asked about. Both branches now read one settling
window keyed on `infoPanelContainer` -- the one element present on both
readings, and the one both clicks land inside.

**The second half is that a settling guard alone is not enough either.**
`ensureInfoPanelLocationInfoIsExpanded` is reached from
`generalSetupInUserInterface`, above the pod recovery and above
`branchDependingOnDockedOrInSpace`, so every reading on which it answers `Just`
is a reading on which `runAwayIfLowHealth` is unreachable. A guard that answered
`waitForProgressInGame` while it settled would have held the tree on five
readings out of every six rather than six out of six, which is not a bound on
anything that matters. So while a repair click is settling the function answers
`Nothing`: it neither clicks again nor holds the tree.

`TheAlternationTerminatesTest` is the case that says so. It folds the real rule
over the alternation the issue records -- panel absent, panel collapsed, panel
absent -- with each reading's `previousStepsEffects` carrying the effects the
rule itself produced on the reading before, and the panel toggling on every
click exactly as #297 describes. What it asserts is not that the alternation
stops (it is the client doing that, and this change cannot stop it) but that the
bot stops paying for it: at most one reading in `moduleButtonClickSettlingSteps
+ 1` is held, and the rest are given back to the tree.

**Confirmed by mutation**, each one graded on the process exit code with
`NO_COLOR=1`:

  - keying the shared guard on `iconLocationInfoPanel` instead of the container
    -- the per-branch guard this issue argues against -- fails six cases, and
    *which* six is the argument itself.
    `TheCollapsedBranchSeesTheIconsClickTest` still passes under it, because the
    icon is in the tree on the collapsed reading and can be asked about; what
    fails is `TheAbsentBranchSeesTheCollapsedBranchsClickTest`, where the click
    to be noticed was aimed at a panel that is no longer in the tree, plus
    `TheAlternationTerminatesTest.test_two_clicks_are_never_adjacent` and
    `test_the_bot_gets_most_of_its_readings_back`. One direction of the
    alternation is guardable per branch. The other is not, and one is enough to
    keep the loop turning;
  - answering `waitForProgressInGame` rather than `Nothing` while the click
    settles fails twelve, `TheRepairStandsAsideRatherThanHoldingTheTreeTest`
    and `test_no_reading_is_spent_waiting` among them, and leaves
    `test_two_clicks_are_never_adjacent` passing -- which is exactly the shape
    of that mutation: the alternation is broken, the starvation is not;
  - moving the settling window by one in either direction fails three, split
    across the two boundary cases and the fold;
  - reverting all copies of this mechanism to the code this issue was filed on
    fails every behavioural case in this file plus the pins
    in `test_info_panel_icon_click_settling.py`. (`eve-online-mining-bot`'s
    tree has since been replaced with Viir's current upstream and carries none
    of this mechanism at all; it is excluded from every case here.)

**One shape this file used to fold over has no app any more.** A
`StepDecisionContext` carrying `previousStepEffects : List
EffectOnWindowStructure` -- one step of history rather than several -- bought a
narrower bound, every other reading rather than five in six, and it was the
same property: the repair cannot hold the tree on consecutive readings, so
`runAwayIfLowHealth` stays reachable however long the panel stays broken. Its
only app was `eve-online-wingus`, retired with the 2023 host interface (see
`notes/retire-wingus.md`), so the fold over it went with the app. The finding
is kept here rather than in a deleted class, because it is what says the bound
is a property of the rule and not of how deep a context's history happens to
be -- a future app on a one-step context needs no second design, only a
narrower expectation.

**Executed rather than restated.** Every reading here is a UI tree run through
the real `EveOnline.ParseUserInterface`, and the rule is the one in the app's
own `Bot.elm`'s framework, reached in `elm repl`. The collapsed reading is the
absent reading's container with an `InfoPanelLocationInfo` node added, so the
two fixtures cannot drift apart in the icon wiring that both depend on.

**Not asserted here:** that `(x + 8, y + 8)` is the right place to click. The
issue reads it as the panel's own header corner, which toggles the panel rather
than expanding it; no reading of a collapsed panel's subtree has been captured,
so the target is unverified and unchanged, and these cases are about the click
being bounded rather than about it being right. `TheAlternationTerminatesTest`
is built on the issue's reading of it -- a click that toggles -- because that is
the worst case for the bound, not because it is established.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import unittest

from prerequisites import ElmRepl, open_repl
from test_info_panel_icon_click_settling import (
    EXTRA_PREAMBLE, SIX_VENDORED_FRAMEWORKS, info_panel_container)
from test_saxrat_ported_guards import (
    SaxratRepl, body_of, collapsed, label, node, source_of)

# The container region has to hold both click sites, which is the whole point of
# keying the guard on it: the icon's centre, and the panel's own corner plus
# eight. Written out here rather than left incidental, because a fixture where
# one of them fell outside would make the guard look broken.
ICON_REGION = (10, 5, 20, 16)
COLLAPSED_PANEL_REGION = (0, 30, 150, 20)


def collapsed_location_panel(region):
    """An `InfoPanelLocationInfo` the real parser accepts, drawn short.

    `parseInfoPanelLocationInfoFromInfoPanelContainer` answers `Nothing` for a
    panel with no `ListSurroundingsBtn` under it however well-named the node is,
    so the button is what makes this a panel rather than a node the parser walks
    past -- and a fixture without it would reach the *absent* branch while
    reading as though it were testing the collapsed one.
    """
    return node("InfoPanelLocationInfo", {}, [
        node("ListSurroundingsBtn", {}, region=(4, 2, 16, 16)),
        label("Luromooh <color=0xFF00FF00>0.6</color>", (24, 2, 100, 16)),
    ], region=region)


def container_with_collapsed_panel():
    """The absent reading's container, with a collapsed panel added to it."""
    container = info_panel_container(ICON_REGION)
    container["children"].append(
        collapsed_location_panel(COLLAPSED_PANEL_REGION))
    return container


class RepairRepl(ElmRepl):
    """Both readings, the rule, and the fold over the alternation."""

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", EXTRA_PREAMBLE)
        super().__init__(**kwargs)

    HELPERS = [
        SaxratRepl.reading_binding(
            "readingAbsent", [info_panel_container(ICON_REGION)]),
        SaxratRepl.reading_binding(
            "readingCollapsed", [container_with_collapsed_panel()]),
        "iconClickEffects ="
        " readingAbsent |> Maybe.andThen (.infoPanelContainer"
        " >> Maybe.andThen .icons >> Maybe.andThen .locationInfo)"
        " |> Maybe.map (\\icn -> EffectOnWindow.effectsMouseClickAtLocation"
        " EffectOnWindow.MouseButtonLeft (EveOnline.ParseUserInterface"
        ".centerFromDisplayRegion icn.totalDisplayRegionVisible))"
        " |> Maybe.withDefault []",
        # The point the collapsed branch clicks, written the way the branch
        # writes it, so a fixture whose panel sat somewhere else would move both
        # together.
        "panelCornerClickEffects ="
        " readingCollapsed |> Maybe.andThen (.infoPanelContainer"
        " >> Maybe.andThen .infoPanelLocationInfo)"
        " |> Maybe.map (\\panel -> EffectOnWindow.effectsMouseClickAtLocation"
        " EffectOnWindow.MouseButtonLeft"
        " { x = panel.uiNode.totalDisplayRegion.x + 8"
        " , y = panel.uiNode.totalDisplayRegion.y + 8 })"
        " |> Maybe.withDefault []",
        "decisionFor reading steps = reading |> Maybe.andThen"
        " (EveOnline.BotFrameworkSeparatingMemory"
        ".ensureInfoPanelLocationInfoIsExpanded steps)",
        "textOf decision = decision |> Maybe.map (Common.DecisionPath"
        ".unpackToDecisionStagesDescriptionsAndLeaf >> Tuple.first"
        " >> String.join \" | \") |> Maybe.withDefault \"NOTHING\"",
        "resultText reading steps = textOf (decisionFor reading steps)",
        "effectsOf decision =\n"
        "    case decision |> Maybe.map (Common.DecisionPath"
        ".unpackToDecisionStagesDescriptionsAndLeaf >> Tuple.second) of\n"
        "        Just (EveOnline.BotFrameworkSeparatingMemory.ContinueSession"
        " act) ->\n"
        "            act.effectsOnGameClient\n"
        "        _ ->\n"
        "            []",
        # One reading of the alternation, as the client plays it back in #297:
        # the panel is in the tree or it is not, and *any* click of ours flips
        # that. `-` is a reading given back to the rest of the tree, `C` a
        # reading spent clicking, `W` a reading spent waiting.
        "advance _ ( panelPresent, history, log ) =\n"
        "    let\n"
        "        decision =\n"
        "            decisionFor (if panelPresent then readingCollapsed"
        " else readingAbsent) history\n"
        "        effects =\n"
        "            effectsOf decision\n"
        "        clicked =\n"
        "            not (List.isEmpty effects)\n"
        "    in\n"
        "    ( if clicked then not panelPresent else panelPresent\n"
        "    , effects :: history |> List.take 10\n"
        "    , log ++ (case decision of\n"
        "                Nothing -> \"-\"\n"
        "                Just _ -> if clicked then \"C\" else \"W\")\n"
        "    )",
        "alternation readings ="
        " List.foldl advance ( False, [], \"\" ) (List.range 1 readings)"
        " |> (\\( _, _, log ) -> log)",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class SaxratRepairRepl(RepairRepl, SaxratRepl):
    """The same bindings, pointed at saxrat -- the bot the issue was filed on.

    `RepairRepl` first in the MRO for the reason
    `test_info_panel_icon_click_settling.SaxratIconSettlingRepl` gives: its
    `preamble` default has to claim the kwarg before `SaxratRepl.__init__` runs
    its own `setdefault`.
    """


class BothAppsRepl:
    """One repl per app carrying this shape of the declaration."""

    @classmethod
    def setUpClass(cls):
        cls.repls = {"mission runner": open_repl(RepairRepl),
                     "saxrat": open_repl(SaxratRepairRepl)}

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


class TheTwoReadingsAreWhatTheyClaimTest(BothAppsRepl, unittest.TestCase):
    """The fixtures, before anything is concluded from them.

    A collapsed reading the parser made nothing of would reach the *absent*
    branch and pass every case below for the wrong reason.
    """

    def test_the_readings_parse_into_the_two_states(self):
        for app, answers in self.each_bool([
                # Absent: the icon reads, the panel does not.
                "readingAbsent |> Maybe.andThen .infoPanelContainer"
                " |> Maybe.andThen .infoPanelLocationInfo |> (==) Nothing",
                # Collapsed: the panel reads, and reads short enough for the
                # `35 < height` branch to be the one taken.
                "readingCollapsed |> Maybe.andThen .infoPanelContainer"
                " |> Maybe.andThen .infoPanelLocationInfo"
                " |> Maybe.map (.uiNode >> .totalDisplayRegion >> .height"
                " >> (\\h -> h <= 35)) |> Maybe.withDefault False",
                # Both readings still carry the icon, so the absent branch has
                # something to click on either one.
                "readingCollapsed |> Maybe.andThen (.infoPanelContainer"
                " >> Maybe.andThen .icons >> Maybe.andThen .locationInfo)"
                " |> (/=) Nothing",
                "iconClickEffects /= []",
                "panelCornerClickEffects /= []",
        ]):
            self.assertEqual(
                answers, [True, True, True, True, True],
                "%s: fixtures did not parse as intended" % app)

    def test_both_click_sites_land_inside_the_container(self):
        """What the shared guard rests on, asserted rather than assumed.

        The guard is keyed on `infoPanelContainer`; a click site outside it
        would be a click the guard could not see, and the deadlock would come
        back wearing the fix.
        """
        for app, answers in self.each_bool([
                "readingCollapsed |> Maybe.andThen .infoPanelContainer"
                " |> Maybe.map (\\c -> EveOnline.BotFrameworkSeparatingMemory"
                ".doEffectsClickUIElement c.uiNode iconClickEffects)"
                " |> Maybe.withDefault False",
                "readingCollapsed |> Maybe.andThen .infoPanelContainer"
                " |> Maybe.map (\\c -> EveOnline.BotFrameworkSeparatingMemory"
                ".doEffectsClickUIElement c.uiNode panelCornerClickEffects)"
                " |> Maybe.withDefault False",
        ]):
            self.assertEqual(
                answers, [True, True],
                "%s: a repair click lands outside the element the shared "
                "guard is keyed on" % app)


class TheCollapsedBranchSeesTheIconsClickTest(BothAppsRepl, unittest.TestCase):
    """The half of the pair that had no guard at all.

    The reading after the icon click is the collapsed one -- that is what the
    icon click produces -- and on it the collapsed branch used to click
    `(x + 8, y + 8)` straight away, which took the panel back out of the tree
    and handed the absent branch its precondition back.
    """

    def test_the_icons_click_is_waited_out_by_the_other_branch(self):
        for app, (answer,) in self.each(
                ["resultText readingCollapsed [ iconClickEffects ]"]):
            self.assertEqual("NOTHING", answer, app)

    def test_it_is_still_waited_out_five_steps_later(self):
        for app, (answer,) in self.each(
                ["resultText readingCollapsed"
                 " (List.repeat 4 [] ++ [ iconClickEffects ])"]):
            self.assertEqual("NOTHING", answer, app)

    def test_and_clicks_once_the_window_has_passed(self):
        """Not a guard that never lets go: six steps back is outside
        `moduleButtonClickSettlingSteps` and the repair tries again."""
        for app, (answer,) in self.each(
                ["resultText readingCollapsed"
                 " (List.repeat 5 [] ++ [ iconClickEffects ])"]):
            self.assertIn("Location info panel seems collapsed.", answer, app)
            self.assertIn("Click to expand the info panel.", answer, app)


class TheAbsentBranchSeesTheCollapsedBranchsClickTest(
        BothAppsRepl, unittest.TestCase):
    """The other direction, which no per-branch guard could have covered.

    On this reading the panel is not in the tree, so there is no
    `infoPanelLocationInfo` to ask a guard about -- and the click that has to be
    noticed is the one aimed at it. Keying the guard on the container is what
    makes the question answerable at all.
    """

    def test_the_panel_corner_click_is_waited_out_by_the_icon_branch(self):
        for app, (answer,) in self.each(
                ["resultText readingAbsent [ panelCornerClickEffects ]"]):
            self.assertEqual("NOTHING", answer, app)

    def test_and_the_icon_is_clicked_once_the_window_has_passed(self):
        for app, (answer,) in self.each(
                ["resultText readingAbsent"
                 " (List.repeat 5 [] ++ [ panelCornerClickEffects ])"]):
            self.assertIn(
                "Click on the icon to enable the info panel.", answer, app)


class TheRepairStandsAsideRatherThanHoldingTheTreeTest(
        BothAppsRepl, unittest.TestCase):
    """`Nothing`, not `waitForProgressInGame`.

    `generalSetupInUserInterface` takes the first `Just` in its list, so a wait
    here is the pod recovery, the docked-or-in-space split and the retreat all
    unreachable for that reading. #227 left the give-up out deliberately; #297
    is the finding that says it is owed.
    """

    def test_a_settling_click_answers_nothing_on_either_reading(self):
        for app, answers in self.each([
                "resultText readingCollapsed [ iconClickEffects ]",
                "resultText readingAbsent [ panelCornerClickEffects ]",
                "resultText readingCollapsed [ panelCornerClickEffects ]",
                "resultText readingAbsent [ iconClickEffects ]",
        ]):
            self.assertEqual(
                ["NOTHING"] * 4, answers,
                "%s: the repair held the tree while its own click settled"
                % app)


class TheAlternationTerminatesTest(BothAppsRepl, unittest.TestCase):
    """The issue's own shape, folded, and what it costs the bot.

    Every click flips the panel between "in the tree, collapsed" and "not in the
    tree", which is #297's account of the two clicks and the worst case for the
    bound. The rule is handed its own effects as `previousStepsEffects`, capped
    at ten steps the way `lastStepsEffects` caps them.
    """

    READINGS = 40

    def test_the_bot_gets_most_of_its_readings_back(self):
        for app, (log,) in self.each(
                ["alternation %d" % self.READINGS]):
            self.assertEqual(self.READINGS, len(log), "%s: %s" % (app, log))
            held = len(log) - log.count("-")
            self.assertLessEqual(
                held, self.READINGS // 6 + 1,
                "%s: the repair held the tree on %d of %d readings (%s)"
                % (app, held, self.READINGS, log))

    def test_no_reading_is_spent_waiting(self):
        """A wait is a held reading that did not even try a repair."""
        for app, (log,) in self.each(
                ["alternation %d" % self.READINGS]):
            self.assertNotIn("W", log, "%s: %s" % (app, log))

    def test_the_repair_never_gives_up_clicking(self):
        """Bounded is not the same as abandoned: the panel can still come back
        at any time, so the repair goes on trying, once per settling window."""
        for app, (log,) in self.each(
                ["alternation %d" % self.READINGS]):
            self.assertGreaterEqual(
                log.count("C"), self.READINGS // 6 - 1,
                "%s: the repair stopped trying (%s)" % (app, log))

    def test_two_clicks_are_never_adjacent(self):
        """The settling window, seen from the fold rather than asserted about
        one reading: no click is ever followed immediately by another."""
        for app, (log,) in self.each(
                ["alternation %d" % self.READINGS]):
            self.assertNotIn("CC", log, "%s: %s" % (app, log))


class BothBranchesReadOneGuardTest(unittest.TestCase):
    """The shape of the fix, in each vendored copy that carries this mechanism.

    Read through `body_of`'s declaration slice rather than searched for anywhere
    in the file, so a guard that landed in the wrong function would not satisfy
    this.
    """

    def test_the_guard_is_keyed_on_the_container(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path), "infoPanelRepairClickIsSettling"))
            self.assertIn("doEffectsClickUIElement", block, app)
            self.assertIn("infoPanelContainer.uiNode", block, app)
            self.assertNotIn(
                "infoPanelLocationInfo", block,
                "%s: the shared guard is keyed on the panel, which is not in "
                "the tree on the reading the other branch clicks" % app)

    def test_the_rule_asks_that_guard_and_stands_aside(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path),
                        "ensureInfoPanelLocationInfoIsExpanded"))
            self.assertIn(
                "if infoPanelRepairClickIsSettling", block,
                "%s: the rule does not consult the shared guard" % app)
            self.assertRegex(
                block, r"if infoPanelRepairClickIsSettling \S+ \S+ then "
                       r"Nothing",
                "%s: the settling case does not stand aside" % app)

    def test_neither_branch_keeps_a_guard_of_its_own(self):
        """Two guards that cannot see each other is what produced the issue."""
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path),
                        "ensureInfoPanelLocationInfoIsExpanded"))
            self.assertNotIn(
                "doEffectsClickUIElement", block,
                "%s: a per-branch settling check is back in the rule" % app)


class TheClickTargetIsUnchangedAndSaysSoTest(unittest.TestCase):
    """`(x + 8, y + 8)`, and the sentence that admits it is unverified.

    #297 reads that point as the panel's own header corner -- which would make
    the collapsed branch's click actively wrong rather than merely unguarded --
    but no reading of a collapsed panel's subtree exists to settle it. The
    target therefore stays where it was, and the file says why in words rather
    than leaving the next reader to rediscover the question.
    """

    def test_every_copy_still_clicks_the_same_point(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path),
                        "ensureInfoPanelLocationInfoIsExpanded"))
            self.assertIn(
                "totalDisplayRegion.x + 8", block, app)
            self.assertIn(
                "totalDisplayRegion.y + 8", block, app)

    def test_every_copy_records_that_the_target_is_unverified(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = body_of(
                source_of(path), "ensureInfoPanelLocationInfoIsExpanded")
            self.assertIn("**unverified**", collapsed(block), app)


if __name__ == "__main__":
    unittest.main()
