"""Tests for the wingman actually reaching a fleet-mate who is on its grid.

Issue #373, and it was a live outage: all four wingman pilots looping on the
same menu at once, with nothing else in the bot running.

**The cascade was attached to the wrong element.** `goToFleetMate`'s on-grid
branch drove saxrat's `Fleet Member` -> `Warp to Member` cascade from the
*pilot's overview row*. That entry is not in an overview row's menu at all --
it is a submenu of the fleet **broadcast banner's** menu, which is where
`eve-online-saxrat`'s `respondToFleetBackupBroadcast` right-clicks it. #373
captured the whole of a pilot's overview-row menu off the live client while the
bot's own cascade held it open:

    Warp to Within (0 m), Approach, Orbit (5,000 m), Keep at Range (5,000 m),
    Look at, Look At My Ship, Show Info, Overview visibility for Frigate,
    Pilot (Gal Bistot), Broadcast: Target, Broadcast: Repair Target

No `Fleet Member`. So the cascade could not resolve at any range, on any
reading -- not a distance problem and not a timing problem -- and it reopened
the menu forever.

Three things need pinning and each has cases here.

**Two mechanisms, and which one a reading gets.** Where a broadcast from this
pilot is on the banner, saxrat's proven banner cascade is available and is what
runs, `useMenuEntryWithTextEqual` at both rungs because `"Warp to Member"` is a
prefix of `"Warp to Member Within"`. Where no banner names this pilot -- which
is `recoverFromRetreat`'s path -- no context menu is opened at all: the
overview row is selected and the Selected Item panel's own `selectedItemWarpTo`
is pressed, exactly as `warpAwayFromDanger` already does for a celestial in
this same file. The overview row's `Warp to Within` distance flyout is
deliberately not driven, because no run in `~/eve-bot-logs` records that
flyout's entry text and a matcher on a channel nothing has read is #42.

**The bound**, which is the half #373 asked for by name. The banner persists
after a broadcast is answered and a mate at 0 m is a warp the client will not
offer at all, so the steady state after a *successful* arrival is the same
loop. Past `fleetMateWarpAskedReadingsBound` the arm answers `Nothing` and the
drones, the guns, the orbit and the gate get their readings back --
`accelerationGateStep`'s arrangement, and #321's lesson that a branch this high
in the tree with no bound owns the whole bot.

**That `Nothing` reaching the tree**, which is a shape rather than a value: a
give-up that returns a wait is not a give-up, it is the same starvation with a
politer status line. `goToFleetMate`, `actOnBroadcastVerb` and
`recoverFromRetreat` all pass it through.

The cases run the real `Bot.elm` through `elm repl` and read its source.
Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import itertools
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")


class WingmanRepl(ElmRepl):
    """The shared harness, pointed at the wingman."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-fleet-mate-warp-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", ("import Bot exposing (..)",))
        super().__init__(**kwargs)


def step(banner=False, panel_shows=False, panel_offers=False, asked=0):
    """The shipped rule, asked about one reading."""
    return ("fleetMateWarpStep { broadcastBannerNamesThisMate = %s"
            ", panelShowsTheMate = %s"
            ", panelOffersWarpTo = %s"
            ", askedReadings = %s }"
            % (banner, panel_shows, panel_offers, asked))


def elm_bool(value):
    return "True" if value else "False"


def expected_answer(banner, panel_shows, panel_offers):
    """What the two mechanisms come to, restated from the issue rather than
    from the Elm: a banner naming this mate is the client's own Warp to Member,
    and everything else is the panel's two steps."""
    if banner:
        return "WarpToTheMateFromTheBroadcast"
    if not panel_shows:
        return "SelectTheMate"
    if panel_offers:
        return "PressWarpToTheMate"
    return "WaitForTheMatesWarpButton"


class TheFleetMateWarpDecisionTest(unittest.TestCase):
    """The rule itself, executed through the real `Bot.elm`."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_broadcast_from_this_mate_takes_the_banners_own_menu(self):
        """The mechanism saxrat has flown for several hundred broadcasts, and
        the one #373 found attached to the wrong element. It needs no row
        selected first, so it outranks the panel path whenever it is available.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["%s == WarpToTheMateFromTheBroadcast" % step(banner=True),
                 "%s == WarpToTheMateFromTheBroadcast"
                 % step(banner=True, panel_shows=True, panel_offers=True)]),
            [True, True])

    def test_without_a_banner_the_panel_is_driven_in_two_steps(self):
        """`warpAwayFromDanger`'s own arrangement for a celestial: the panel
        acts on whatever is selected, so this is select-then-press and the
        order matters. No context menu is involved at any point."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == SelectTheMate" % step(),
                 "%s == SelectTheMate" % step(panel_offers=True),
                 "%s == WaitForTheMatesWarpButton" % step(panel_shows=True),
                 "%s == PressWarpToTheMate"
                 % step(panel_shows=True, panel_offers=True)]),
            [True, True, True, True])

    def test_the_ask_stops_at_the_bound(self):
        """#373's whole request. Note the state this fires in is the one a
        *successful* arrival produces: the banner is still up, the mate is at
        0 m, and the client offers nothing to warp to."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == WarpToTheMateFromTheBroadcast"
                 % step(banner=True,
                        asked="fleetMateWarpAskedReadingsBound - 1"),
                 "%s == GaveUpOnReachingTheMate"
                 % step(banner=True, asked="fleetMateWarpAskedReadingsBound"),
                 "%s == GaveUpOnReachingTheMate"
                 % step(banner=True,
                        asked="fleetMateWarpAskedReadingsBound + 500")]),
            [True, True, True])

    def test_the_give_up_is_asked_before_every_fact(self):
        """`approachFleetCommanderStep`'s ordering, for its reason: a spent budget
        must never be masked by a moment that happens to look actionable. Every
        one of the eight fact combinations gives up once the budget is gone."""
        combinations = list(itertools.product([False, True], repeat=3))
        expressions = [
            "%s == GaveUpOnReachingTheMate"
            % step(banner=elm_bool(banner),
                   panel_shows=elm_bool(shows),
                   panel_offers=elm_bool(offers),
                   asked="fleetMateWarpAskedReadingsBound")
            for banner, shows, offers in combinations]
        self.assertEqual(self.repl.evaluate(expressions),
                         [True] * len(combinations))

    def test_the_bound_is_a_stated_round_number(self):
        """Thirty, the same allowance the other two-rung cascade in this file
        gets, and written out rather than composed from it -- the two ends have
        nothing to do with each other. This bot still has no corpus of its own
        (see WINGMAN.md), so the number is a choice and the status line is what
        would replace it with a measurement."""
        self.assertEqual(
            self.repl.evaluate(
                ["fleetMateWarpAskedReadingsBound == 30",
                 "fleetMateWarpHasBeenGivenUpOn"
                 " (fleetMateWarpAskedReadingsBound - 1) == False",
                 "fleetMateWarpHasBeenGivenUpOn"
                 " fleetMateWarpAskedReadingsBound == True"]),
            [True, True, True])

    def test_every_combination_of_the_three_facts_lines_up(self):
        """All eight at a fresh counter, so a swapped or dropped condition is
        caught rather than only the combinations somebody thought to write
        down."""
        combinations = list(itertools.product([False, True], repeat=3))
        expressions = [
            "%s == %s" % (step(banner=elm_bool(banner),
                               panel_shows=elm_bool(shows),
                               panel_offers=elm_bool(offers)),
                          expected_answer(banner, shows, offers))
            for banner, shows, offers in combinations]
        self.assertEqual(self.repl.evaluate(expressions),
                         [True] * len(combinations))


class TheTwoMechanismsTest(unittest.TestCase):
    """Which element each cascade is driven from, source-pinned.

    A suite that only exercised `fleetMateWarpStep` would pass on the bot #373
    was filed against: the rule can name the right answer while the branch
    taking it clicks the wrong node. Every needle below is taken from a slice
    that starts at a definition line or a `case` arm, never from the whole
    file -- the doc comment on `warpToFleetMateOnThisGrid` quotes #373's live
    menu capture verbatim, so a needle allowed to match a comment would find
    `Fleet Member` and `Warp to Within` in exactly the function that must not
    contain them.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def body_of(self, definition_line):
        """A function's code, from its definition line to the blank lines that
        end it -- which starts *after* its doc comment.

        Anchored to the start of a line, so a call to the function elsewhere
        cannot stand in for its definition."""
        anchor = "\n" + definition_line
        self.assertIn(anchor, self.source)
        start = self.source.index(anchor) + 1
        return self.source[start:self.source.index("\n\n\n", start)]

    def arm_of(self, definition_line, opening, closing):
        body = self.body_of(definition_line)
        self.assertIn(opening, body)
        self.assertIn(closing, body)
        return body[body.index(opening):body.index(closing)]

    def test_the_on_grid_branch_never_drives_a_menu_off_the_overview_row(self):
        """#373 itself. `Fleet Member` belongs to the broadcast banner's menu
        and has never been in an overview row's, so a cascade attached to the
        row cannot resolve at any range and retries forever."""
        body = self.body_of(
            "warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =")
        self.assertNotIn("useContextMenuCascadeOnOverviewEntry", body)

    def test_the_banner_path_is_saxrats_cascade_unchanged(self):
        """Right-click the banner, `Fleet Member`, `Warp to Member`, matched
        with `useMenuEntryWithTextEqual` at both rungs -- `"Warp to Member"` is
        a prefix of `"Warp to Member Within"` and a containing match takes the
        wrong entry.

        **The cascade is a declaration of its own since #385**, because the
        backup-call arm drives the same rungs for a caller who may have no
        overview row to select. What it must not become is two copies: this
        asserts the rungs where they now live, and that the branch reaches them
        rather than writing its own.
        """
        arm = self.body_of("warpToFleetMateFromTheBroadcastBanner context banner =")
        self.assertIn('useContextMenuCascade\n', arm)
        self.assertIn('( "fleet broadcast", banner )', arm)
        self.assertIn("warpToMemberFromTheBroadcastBanner", arm)

        # The rungs moved into that declaration when the client turned out to
        # offer `Warp to Member` in two different places -- directly on a
        # `needs backup` banner, inside the `Fleet Member` submenu otherwise,
        # both read live off the same element. What must not weaken is the
        # *exactness*: `"Warp to Member"` is a prefix of
        # `"Warp to Member Within"`, so a containing match at either rung takes
        # the wrong entry and warps to a range nobody asked for.
        cascade = self.body_of("warpToMemberFromTheBroadcastBanner =")
        self.assertIn("menuEntryIsWarpToMember", cascade)
        self.assertIn('menuEntryTextEquals "Fleet Member"', cascade)
        self.assertIn('useMenuEntryWithTextEqual "Warp to Member"', cascade)
        self.assertIn("menuCascadeCompleted", cascade)
        self.assertNotIn("stringContainsIgnoringCase", cascade)
        self.assertNotIn("String.startsWith", cascade)
        self.assertNotIn("String.contains", cascade)

        # The comparison is the one `useMenuEntryWithTextEqual` makes, so the
        # direct rung and the submenu rung cannot come to disagree.
        equals = self.body_of("menuEntryTextEquals expected entry =")
        self.assertIn("String.trim", equals)
        self.assertIn("String.toLower", equals)
        self.assertIn("==", equals)

        # Still one copy of the cascade, which is what #385 bought.
        self.assertEqual(
            self.source.count("warpToMemberFromTheBroadcastBanner =\n"), 1)
        self.assertIn(
            "warpToFleetMateFromTheBroadcastBanner context banner",
            self.arm_of(
                "warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =",
                "WarpToTheMateFromTheBroadcast ->",
                "SelectTheMate ->"))

    def test_the_banner_only_counts_while_it_names_this_mate(self):
        """The banner is a *last broadcast* display and does not clear, so "a
        banner is present" is not "this pilot is calling". `recoverFromRetreat`
        is precisely the caller that arrives with somebody else's banner still
        up, and driving `Fleet Member` off it would warp this ship to the wrong
        pilot."""
        body = self.body_of(
            "fleetMateBroadcastBannerElement followFleetBroadcastFrom pilot"
            " readingFromGameClient =")
        self.assertIn("fleetMateCallingForCompany", body)
        self.assertIn("== Just pilot", body)

    def test_the_banner_less_path_presses_the_panels_own_button(self):
        """`warpAwayFromDanger`'s proven mechanism, reused rather than
        reinvented: select the row, then press `selectedItemWarpTo`. No menu,
        so no flyout to guess at."""
        body = self.body_of(
            "warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =")
        self.assertIn('selectedItemButtonNamed context.readingFromGameClient'
                      ' "selectedItemWarpTo"', body)
        select = self.arm_of(
            "warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =",
            "SelectTheMate ->",
            "WaitForTheMatesWarpButton ->")
        self.assertIn("clickUiElementForNavigation overviewEntry.uiNode",
                      select)
        press = self.body_of(
            "warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =")
        press = press[press.index("PressWarpToTheMate ->"):]
        self.assertIn("clickUiElementForNavigation button", press)

    def test_no_distance_flyout_entry_is_guessed_at(self):
        """No run in `~/eve-bot-logs` records the `Warp to Within` flyout's
        entry text, so a matcher written for it would be a matcher on a channel
        nothing has read -- #42's shape, and the reason the panel button path
        exists at all."""
        for guessed in ("Warp to Within", "Within 0 m", "Warp To Within"):
            with self.subTest(guessed=guessed):
                self.assertNotIn(
                    guessed,
                    self.body_of("warpToFleetMateOnThisGrid context pilot"
                                 " calledIt overviewEntry ="))

    def test_the_two_callers_get_the_two_paths(self):
        """The banner path is reached from the broadcast verbs that put a
        banner up; the panel path is what is left for `recoverFromRetreat`,
        which has none.

        **`NeedBackup` is deliberately not among them since #385.** That verb
        has its own arm, its own bound and its own trust boundary, so leaving
        it here would advance `goToFleetMateWarpAskedReadings` and make
        `describeFleetMateWarp` report a warp no branch was attempting.
        """
        body = self.body_of(
            "fleetMateCallingForCompany followFleetBroadcastFrom"
            " readingFromGameClient =")
        for verb in ("AtLocation", "InPositionAt"):
            with self.subTest(verb=verb):
                self.assertIn(verb, body)
        self.assertNotIn("NeedBackup", body)
        self.assertIn("List.member pilot followFleetBroadcastFrom", body)


class TheGiveUpReachesTheTreeTest(unittest.TestCase):
    """A give-up that waits is not a give-up.

    This arm sits above the drones, the guns, the orbit and the gate. #321's
    lesson is that a branch that high with no bound owns the whole bot, and a
    bound whose answer is `waitForProgressInGame` leaves that exactly as it
    was. So `Nothing` has to travel all the way out of `goToFleetMate`, out of
    `actOnBroadcastVerb` and out of `recoverFromRetreat`.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def body_of(self, definition_line):
        anchor = "\n" + definition_line
        self.assertIn(anchor, self.source)
        start = self.source.index(anchor) + 1
        return self.source[start:self.source.index("\n\n\n", start)]

    def test_the_give_up_answers_nothing(self):
        body = self.body_of(
            "warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =")
        give_up = body[body.index("GaveUpOnReachingTheMate ->"):
                       body.index("WarpToTheMateFromTheBroadcast ->")]
        self.assertNotIn("waitForProgressInGame", give_up)
        self.assertNotIn("describeBranch", give_up)
        self.assertIn("Nothing", give_up)

    def test_the_three_signatures_carry_it_out(self):
        """Each of the three used to return a `DecisionPathNode`, which is a
        type with no way to say "I have nothing to do"."""
        for signature in (
                "warpToFleetMateOnThisGrid : BotDecisionContext -> String"
                " -> String -> OverviewWindowEntry -> Maybe DecisionPathNode",
                "goToFleetMate : BotDecisionContext -> ShipUI -> String"
                " -> String -> String -> Maybe DecisionPathNode",
                "actOnBroadcastVerb : BotDecisionContext -> ShipUI -> String"
                " -> Maybe DecisionPathNode"):
            with self.subTest(signature=signature.split(" :")[0]):
                self.assertIn(signature, self.source)

    def test_the_broadcast_arm_does_not_re_wrap_it(self):
        """`actOnFleetBroadcast` used to answer `Just (actOnBroadcastVerb ...)`,
        which would turn the give-up back into a decision before it ever
        reached the tree."""
        self.assertNotIn("Just (actOnBroadcastVerb", self.source)

    def test_the_recovery_arm_does_not_re_wrap_it_either(self):
        """`recoverFromRetreat` describes the branch by mapping over the
        answer, so a `Nothing` stays a `Nothing` and the arms below it get the
        reading.

        The **property** rather than one spelling of it. #381 rewrote this arm
        around a step rule with five answers that hand the reading back, and
        the version that spelled the naming as one `Maybe.map` over a nested
        `case` is gone -- so what is asserted is that the naming still runs
        through `Maybe`, that the arm still reaches `goToFleetMate`, and that
        nothing in it parks on `waitForProgressInGame`. That last clause is
        what a re-wrap would have to break, and it is stronger than the string
        it replaces: the old shape could have wrapped a wait and passed.
        """
        body = self.body_of("recoverFromRetreat context shipUI =")
        self.assertIn("goToFleetMate context shipUI commander", body)
        self.assertIn('describeBranch "Recovering from a retreat', body)
        self.assertRegex(body, r"Maybe\.(map|andThen)")
        self.assertNotIn("waitForProgressInGame", body)


class TheCounterTest(unittest.TestCase):
    """The counter the bound reads, and what advances it.

    #102 is the defect this shape exists against: `abandonMissionGiveUpReadings`
    was a correct comparison over a counter advanced on every reading while the
    branch that read it was reached on 0.7% of them. So the memory update asks
    the same question the decision asks, through the same function, rather than
    restating it.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()
        start = cls.source.index(
            "updateMemoryForNewReadingFromGame context botMemoryBefore =")
        cls.update = cls.source[start:cls.source.index(
            "\n\n\ngetCurrentAnomalyIDAsSeenInProbeScanner", start)]

    def test_the_update_resolves_the_mate_through_the_shipped_rule(self):
        self.assertIn("fleetMateToWarpToOnThisGrid", self.update)
        self.assertIn("recoveringFromRetreat = botMemoryBefore"
                      ".recoveringFromRetreat", self.update)
        self.assertIn("followFleetBroadcastFrom = context.botSettings"
                      ".followFleetBroadcastFrom", self.update)

    def test_the_counter_has_exactly_the_three_arms_it_should(self):
        """Reset, hold, advance -- the shape `test_ammo_silenced_bound` was
        rewritten to assert after it turned out to pass with the counter pinned
        at a constant. Reset when no mate is on this grid, hold once the budget
        is spent so the status line's "after N readings" stays meaningful, and
        advance otherwise.

        **The budget the three arms carry is `fleetMateWarpAskedReadingsCarriedIn`
        since #428**, which is `botMemoryBefore.goToFleetMateWarpAskedReadings`
        refilled by a warp that has just landed. The arms are the same three;
        what changed is what they carry, and
        `test_wingman_landing_refills_the_budget` is where that is executed.
        """
        start = self.update.index(", goToFleetMateWarpAskedReadings =")
        clause = self.update[start:self.update.index(
            "\n    , routeFirstMarkerRegion", start)]
        self.assertIn("if fleetMateOnThisGrid == Nothing then\n            0",
                      clause)
        self.assertIn("fleetMateWarpHasBeenGivenUpOn "
                      "fleetMateWarpAskedReadingsCarriedIn", clause)
        self.assertIn("fleetMateWarpAskedReadingsCarriedIn + 1", clause)
        self.assertEqual(
            clause.count("fleetMateWarpAskedReadingsCarriedIn"), 3)
        self.assertNotIn("botMemoryBefore.goToFleetMateWarpAskedReadings",
                         clause)

    def test_the_budget_the_three_arms_carry_is_the_shipped_refill(self):
        """#428, and the half only this file can see: the counter's own arms
        read a budget the shared refill rule produced from
        `botMemoryBefore.goToFleetMateWarpAskedReadings`, so a rename that left
        the arms reading something else would pass the case above."""
        start = self.update.index("fleetMateWarpAskedReadingsCarriedIn =\n")
        binding = self.update[start:self.update.index("\n\n", start)]
        self.assertIn("askedReadingsRefilledByLanding", binding)
        self.assertIn("justLanded = weJustFinishedWarping", binding)
        self.assertIn("spentBefore = botMemoryBefore"
                      ".goToFleetMateWarpAskedReadings", binding)

    def test_the_bound_is_read_through_one_comparison(self):
        """The step rule and the status clause ask
        `fleetMateWarpHasBeenGivenUpOn`, so a give-up decided in one place and
        reported in another cannot disagree about whether it happened."""
        self.assertIn("fleetMateWarpAskedReadingsBound <= askedReadings",
                      self.source)
        self.assertEqual(
            self.source.count("fleetMateWarpHasBeenGivenUpOn "), 4)

    def test_the_give_up_is_visible_in_the_status_line(self):
        """The arm answers `Nothing`, so without this a ship that stopped
        trying reads exactly like a grid with no fleet-mate on it -- which is
        the shape that made this class of bug hard to see from a console."""
        self.assertIn("describeFleetMateWarp context", self.source)
        self.assertIn('"Warp to a fleet-mate: "', self.source)
        self.assertIn('"GAVE UP after "', self.source)
        self.assertIn("goToFleetMateWarpAskedReadings = 0", self.source)


if __name__ == "__main__":
    unittest.main()
