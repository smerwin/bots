"""The ship cards a reading can be acted on, and the tab that reveals them.

The station panel keeps the Ships tab's cards in the UI tree while a different
tab is showing: display regions intact, and no `_display` to say otherwise.
That is the overview's virtualised-row shape in a second widget, and it has the
same consequence -- right-clicking one lands on whatever the *visible* tab has
put in that place.

Watched live on 2026-08-16, on a character with seven ships in the hangar. With
the Agents tab selected, the restock's right-click aimed at card 0 (an Omen Navy
Issue) opened an agent's context menu instead -- `Show Info`,
`Start Conversation`, `Add Waypoint`, `Save Location...`,
`Remove from Addressbook` -- and the cascade then failed to find "Open Drone
Bay" for as long as the maintenance window lasted. A screenshot of the same
reading shows the Agents tab selected and no ship card on screen.

**The bot puts itself into that state**, which is what makes this worth a guard
rather than a note: `surveyAgentsInStation` selects the Agents tab and nothing
puts it back, so a session that surveys leaves the *next* session's restock
right-clicking agents. The two tasks are the two entries of
`maintenanceWhileDocked`, and their own ordering comment argues only that their
*time* windows do not overlap -- which is true, and does not stop one leaving
client state the other cannot work from.

The rules are executed through the real `Bot.elm` in `elm repl`, and the
readings they are asked about are built by the real
`EveOnline.ParseUserInterface` -- a Python restatement of "what does this
parser make of this tree" would test the restatement. `shipItemCards` is
asserted non-empty in the same breath as `shipItemCardsOnScreen` being empty,
so a fixture that simply failed to parse any card cannot pass these.
"""

import unittest

from prerequisites import open_repl
from test_quick_message_logged import (
    MISSION_RUNNER_BOT_ELM, MissionRunnerRepl, collapsed, declaration,
    label, node, reading_binding, source_of)


def agents_tab(selected):
    """The station lobby, with its Agents tab selected or not.

    `LobbyWnd` is what `parseStationWindowFromUITreeRoot` looks for, and the tab
    is found by `_name` rather than by text -- both read off the real parser
    rather than guessed.
    """
    return node("LobbyWnd", {"_name": "lobby"}, [
        node("Tab",
             {"_name": "stationInformationTabAgents", "_selected": selected},
             region=(1616, 382, 100, 32)),
    ], region=(1600, 370, 300, 800))


def ship_cards(count):
    """`count` ship cards, laid out as the live panel lays them out.

    112 points apart starting at y=486, which is what the client drew on the
    reading this was found on.
    """
    return [
        node("ShipItemCard", {"_name": "shipCard"},
             [label("Auspicious" if index == 0 else "Impairor",
                    region=(1620, 490 + index * 112, 200, 20))],
             region=(1616, 486 + index * 112, 254, 106))
        for index in range(count)
    ]


def hangar_tab_labels():
    """The two labels `shipHangarTabToOpen` chooses between.

    Both are present in the tree at once in the state this is about -- which is
    the whole difficulty, since the hidden one is as findable as the visible
    one.
    """
    return [
        label("Ships", region=(1616, 414, 60, 20)),
        label("Hangars", region=(1838, 382, 80, 20)),
    ]


class ShipCardsOffScreenRepl(MissionRunnerRepl):
    """The mission runner's own compiled code, answering for itself."""


class TheCardsAreNotTrustedWhileAnotherTabIsShowing(unittest.TestCase):
    """`shipItemCardsOnScreen` is what the ship-card path may act on."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ShipCardsOffScreenRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parsed(self, name, agents_selected, cards=7):
        return reading_binding(
            name, [agents_tab(agents_selected)] + ship_cards(cards))

    def test_the_agents_tab_hides_every_card(self):
        """The live failure: seven cards in the tree, none of them actionable.

        Both halves are asserted together. "No card is on screen" is the claim,
        and "seven cards parsed" is what stops a fixture that parsed nothing
        from satisfying it -- which is the way this case would otherwise pass
        having tested nothing.
        """
        on_screen_empty, cards_really_parsed = self.repl.evaluate(
            ["reading |> Maybe.map"
             " (\\r -> List.isEmpty (shipItemCardsOnScreen r))"
             " |> Maybe.withDefault False",
             "reading |> Maybe.map (\\r -> List.length r.shipItemCards == 7)"
             " |> Maybe.withDefault False"],
            definitions=[self.parsed("reading", True)])
        self.assertTrue(cards_really_parsed,
                        "the fixture's seven ShipItemCards did not parse, so "
                        "the emptiness below would prove nothing")
        self.assertTrue(on_screen_empty,
                        "a card was offered while the Agents tab was selected "
                        "-- this is the right-click that opened an agent menu")

    def test_the_cards_are_offered_when_the_panel_is_showing_them(self):
        """The ordinary case has to keep working, or the restock never runs."""
        offered, = self.repl.evaluate(
            ["reading |> Maybe.map"
             " (\\r -> List.length (shipItemCardsOnScreen r) == 7)"
             " |> Maybe.withDefault False"],
            definitions=[self.parsed("reading", False)])
        self.assertTrue(offered,
                        "the cards were withheld with the Agents tab "
                        "unselected, which would stop the restock entirely")

    def test_a_reading_with_no_station_window_is_unchanged(self):
        """No lobby, no claim.

        The guard is about one known way the cards go off screen. A reading that
        cannot answer the question is left exactly as it was before this rule
        existed, rather than having the cards withheld on a guess -- withholding
        them costs the restock, and nothing here is evidence for it.
        """
        offered, = self.repl.evaluate(
            ["reading |> Maybe.map"
             " (\\r -> List.length (shipItemCardsOnScreen r) == 3)"
             " |> Maybe.withDefault False"],
            definitions=[reading_binding("reading", ship_cards(3))])
        self.assertTrue(offered,
                        "cards were withheld from a reading with no station "
                        "window, which is a guess rather than a reading")

    def test_no_cards_at_all_stays_no_cards(self):
        """The state the recovery was already written for is untouched."""
        empty_hidden, empty_shown = self.repl.evaluate(
            ["reading |> Maybe.map"
             " (\\r -> List.isEmpty (shipItemCardsOnScreen r))"
             " |> Maybe.withDefault False"
             for reading in ("reading", "reading")],
            definitions=[self.parsed("reading", True, cards=0)])
        self.assertTrue(empty_hidden and empty_shown)


class TheRecoveryClicksATabThatIsActuallyVisible(unittest.TestCase):
    """Which tab `shipHangarTabToOpen` offers, and why it is not always Ships.

    The "Ships" strip is the Hangars tab's own content, so while another tab is
    showing it is hidden-but-present in exactly the way the cards are. Clicking
    it would land on a row belonging to the visible tab -- the same failure the
    guard above exists to stop, one step later.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ShipCardsOffScreenRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def tab_offered(self, agents_selected, cards):
        answer, = self.repl.strings(
            ["reading |> Maybe.andThen shipHangarTabToOpen"
             " |> Maybe.map Tuple.first |> Maybe.withDefault \"none\""],
            definitions=[reading_binding(
                "reading",
                [agents_tab(agents_selected)]
                + ship_cards(cards) + hangar_tab_labels())])
        return answer

    def test_hidden_cards_are_revealed_with_the_hangars_tab(self):
        """Both labels are in the tree; only one of them is on screen."""
        self.assertEqual(
            self.tab_offered(agents_selected=True, cards=7), "Hangars",
            "the recovery offered the Ships strip, which is hidden in the same "
            "way the cards are -- clicking it lands on the visible tab's rows")

    def test_a_panel_with_no_cards_at_all_still_prefers_ships(self):
        """The pre-existing behaviour, which this must not disturb.

        With no cards in the tree there is nothing to say another tab is
        showing, so the original order stands and "Ships" is taken when it is
        there. That is the state `openDroneBayFromShipCard` was already written
        for, and run 3 of the live probe reached it.
        """
        self.assertEqual(
            self.tab_offered(agents_selected=False, cards=0), "Ships")

    def test_the_hangars_preference_is_about_hiding_not_about_agents(self):
        """Cards on screen and a selected Agents tab cannot both be true.

        Asked so the rule is pinned to "the cards are hidden" rather than to
        "an agent tab exists", which are the same answer on every fixture above
        and different ones here.
        """
        self.assertEqual(
            self.tab_offered(agents_selected=False, cards=7), "Ships")


class TheWiringIsWhatMakesAnyOfThisReachable(unittest.TestCase):
    """The guard has to be what the ship-card path actually consults.

    Read out of the source through a whitespace-collapsing reader, so an
    `elm-format` pass cannot break the assertion the way it has broken three
    others in this repo.
    """

    def setUp(self):
        self.source = source_of(MISSION_RUNNER_BOT_ELM)

    def test_the_ship_card_path_reads_the_guard(self):
        body = collapsed(declaration(self.source, "openDroneBayFromShipCard"))
        self.assertIn("shipItemCardsOnScreen context.readingFromGameClient",
                      body,
                      "the branch that right-clicks a card is not asking which "
                      "cards are on screen")

    def test_the_ship_card_path_does_not_reach_past_the_guard(self):
        """The raw field is the thing that was wrong; it must not be read here.

        A version that consults the guard *and* keeps the old lookup would pass
        the case above while behaving exactly as it did before.
        """
        body = collapsed(declaration(self.source, "openDroneBayFromShipCard"))
        self.assertNotIn("readingFromGameClient.shipItemCards", body,
                         "the branch still reads the unfiltered card list")

    def test_the_guard_is_keyed_on_the_tab_rather_than_on_the_cards(self):
        """The cards say nothing that separates the two states.

        Every card carries a display region and no `_display` whichever tab is
        showing, which is why this is keyed on `agentsTab.isSelected`. A guard
        that tried to read the answer off the cards would be reading a field
        that is identical in both.
        """
        body = collapsed(declaration(self.source, "shipItemCardsOnScreen"))
        self.assertIn("agentsTab.isSelected", body)

    def test_the_recovery_consults_the_same_guard(self):
        """One notion of "on screen", not two that can disagree."""
        body = collapsed(declaration(self.source, "shipHangarTabToOpen"))
        self.assertIn("shipItemCardsOnScreen", body)


if __name__ == "__main__":
    unittest.main()
