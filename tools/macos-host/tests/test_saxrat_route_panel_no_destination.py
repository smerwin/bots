"""Tests for a route panel that says 'No Destination' beside a stale marker.

Issue #191. saxrat run 23 spent **1,200+ consecutive readings** on

    No stargate on the overview is named for 'Hutian' -- right-click the route
    marker instead.

and never moved. It was not stuck in a loop of its own making: it was travelling
a route the client had never computed. Read off the live client while it was
stuck, the panel carried both of these at once, with one marker icon:

    No Destination
    <a href="showinfo:5//30002217" alt="Next System in Route">Hutian</a>
    No Destination

Setting three destinations from the same position showed the client was fine --
`Hamse` gave `Route 5 Jumps`, `Amarr` gave `Route 6 Jumps`, and `Hutian` gave no
route and one stale pip. So `hunt-system` can hold a system the client will not
route to, and the circuit rotates onto it eventually, which parks the run.

**Why reading the words is the fix rather than a counter.**
`infoPanelRouteFirstMarkerFromReadingFromGameClient` answers the panel's
*visibility* and has never read its text, so a stale pip reads as a route. The
travel leg it feeds is a fall-back to a cascade and has no bound at all --
whereas *asking* for a route is bounded by `routeAskGiveUpReadings` and ends in
the hunt circuit moving on. Letting the reading reach the branch that already has
a bound is what ends the loop; a second counter here would only have made the
parking quieter.

The rules are executed through the real `Bot.elm` in `elm repl`, against trees
built by the real `EveOnline.ParseUserInterface`.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, node, source_of)

# Verbatim from the live client while run 23 was stuck.
STALE_LABEL = ('<a href="showinfo:5//30002217" alt="Next System in Route">'
               'Hutian</a>')
NO_DESTINATION = "No Destination"


def route_panel(texts):
    """An info panel container holding a route panel with `texts` in it."""
    return node("InfoPanelContainer", {"_name": "infoPanelContainer"}, [
        node("InfoPanelRoute", {"_name": "infoPanelRoute"},
             [node("EveLabelSmall", {"_setText": text}, [], region=(0, i * 12, 200, 12))
              for i, text in enumerate(texts)],
             region=(0, 0, 200, 60)),
    ], region=(0, 0, 200, 60))


class TheStaleMarkerIsCaughtByTheWordsBesideItTest(unittest.TestCase):
    """`routePanelSaysNoDestination`, against the reading that produced #191."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def says_no_destination(self, texts):
        return self.repl.evaluate(
            ["(r |> Maybe.map routePanelSaysNoDestination"
             " |> Maybe.withDefault False)"],
            [SaxratRepl.reading_binding("r", [route_panel(texts)])])[0]

    def test_run_23s_own_panel_is_read_as_having_no_destination(self):
        """Both at once, which is the whole issue."""
        self.assertTrue(self.says_no_destination(
            [NO_DESTINATION, STALE_LABEL, NO_DESTINATION]))

    def test_a_panel_that_only_says_it_is_read_the_same_way(self):
        self.assertTrue(self.says_no_destination([NO_DESTINATION]))

    def test_a_real_route_is_not_read_as_having_no_destination(self):
        """The panel as it reads while the client has computed a route."""
        self.assertFalse(self.says_no_destination(
            ["Route 5 Jumps", "Next System in Route: Otelen",
             "Current Destination: Hamse"]))

    def test_a_panel_with_only_the_label_is_not_read_as_having_none(self):
        """A stale label alone is not evidence either way, and this rule does
        not claim it is -- what it reads is the client's own sentence."""
        self.assertFalse(self.says_no_destination([STALE_LABEL]))

    def test_the_casing_the_client_uses_is_not_relied_on(self):
        for text in ["NO DESTINATION", "no destination", "No destination"]:
            with self.subTest(text):
                self.assertTrue(self.says_no_destination([text]))


class TheTravelLegDefersToTheWordsTest(unittest.TestCase):
    """Where the answer is consulted, read out of the branch itself.

    The failure this pins is the branch being added and then not reached: a
    reader that answers correctly while `jumpToNextSystem` goes on asking the
    marker first would leave run 23 exactly as it was.
    """

    @classmethod
    def setUpClass(cls):
        cls.branch = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                       "jumpToNextSystem"))

    def test_the_words_are_asked_before_the_marker(self):
        self.assertLess(
            self.branch.index("routePanelSaysNoDestination"),
            self.branch.index("infoPanelRouteFirstMarkerFromReadingFromGameClient"),
            "a stale marker is only stale if the words are read first")

    def test_it_answers_by_asking_for_a_route_rather_than_by_waiting(self):
        """`setRouteToNextHuntingGround` is the branch carrying the bound.

        Waiting here, or describing and handing the reading back, would leave
        the session parked exactly as #191 describes -- quietly rather than
        loudly, which is worse.
        """
        after = self.branch[self.branch.index("routePanelSaysNoDestination"):]
        first_answer = after[:after.index("else")]
        self.assertIn("setRouteToNextHuntingGround context", first_answer)
        self.assertNotIn("waitForProgressInGame", first_answer)

    def test_the_operator_is_told_which_of_the_two_readings_won(self):
        """A stretch of these in the log is the diagnosis, so it has to say
        that the marker was the thing disbelieved."""
        self.assertIn("marker is stale", self.branch)


class TheReaderIsNotADuplicateTest(unittest.TestCase):
    """One place decides whether the panel says there is no destination."""

    @classmethod
    def setUpClass(cls):
        cls.source = collapsed(source_of(SAXRAT_BOT_ELM))

    def test_the_marker_text_is_named_once_rather_than_inline(self):
        self.assertIn('routePanelNoDestinationMarker = "no destination"',
                      self.source)

    def test_nothing_else_matches_that_phrase_by_hand(self):
        """A second inline copy is what drifts when the client rewords."""
        self.assertEqual(self.source.count('"no destination"'), 1)


if __name__ == "__main__":
    unittest.main()
