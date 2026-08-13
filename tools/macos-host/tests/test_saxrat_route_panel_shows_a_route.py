"""Tests for reading the route panel one way rather than two (issue #191).

`No Destination` is not the absence of a route. It is a label the client leaves
in the tree under a node whose own `_name` is `noDestinationLabel`, and it can
sit beside a perfectly good route. Two captures are what this rests on, and they
are the two ways the bot got stuck:

- **run 23** -- `No Destination`, a `Next System in Route` label, `No Destination`
  again, and one marker pip, with no route the client had ever computed. The bot
  followed the pip and travelled a route that did not exist, 1,200+ readings.
- **run 31** -- `Route 5 Jumps`, the same stale `No Destination`, a
  `Next System in Route` label and a `Current Destination` label, with a real
  five-jump route the bot had just set through ESI. The bot read the words,
  concluded there was no route, and asked the host for one **2,494 times in 48
  minutes**.

Those two cannot be separated by the presence of a pip, nor by the presence of
`No Destination`, nor by `Next System in Route` -- every one of those appears in
both. What separates them is `Current Destination` and the jump count, which is
why the rule is stated positively.

The second half of #191 is that the bot asked the panel *two different
questions*. `jumpToNextSystem` tested the words and `standingInADeadEnd` -- the
counter that bounds the asking -- tested the pip, so with a real route beside a
stale label the decision asked forever while its own bound stayed at zero. Run
31 printed `0/20 readings` on all 2,494 of them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import SAXRAT_BOT_ELM, SaxratRepl, body_of
from test_saxrat_route_stargate_panel_jump import route_panel

# Read off the live client while run 31 was stuck in Hama, verbatim.
RUN_31_HAS_A_ROUTE = [
    "Route <fontsize=12>5 Jumps",
    "No Destination",
    '<center><a href="showinfo:5//30003525" alt="Next System in Route">Bagodan</a>',
    '<center><a href="showinfo:5//30003547" alt="Current Destination">Hamse</a>',
]

# Run 23's, as `routePanelSaysNoDestination`'s own doc comment records it.
RUN_23_HAS_NO_ROUTE = [
    "No Destination",
    '<a href="showinfo:5//30002217" alt="Next System in Route">Hutian</a>',
    "No Destination",
]


class RoutePanelRepl(SaxratRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-routepanel-repl-")
        super().__init__(**kwargs)


class TheTwoCapturesAreToldApartTest(unittest.TestCase):
    """The whole point: one rule, both recorded shapes, opposite answers."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RoutePanelRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def answers(self, labels):
        """`(showsARoute, saysNoDestination)` for a panel holding `labels`.

        The parse is asserted first. `Maybe.withDefault False` below would turn
        a fixture that never arrived into two confident `False`s, and a case
        over a reading that was never built proves nothing -- which is exactly
        the failure `elm_json_literal`'s doc comment exists for.
        """
        definition = self.repl.reading_binding("reading", [route_panel(labels)])
        parsed, shows, says_none = self.repl.evaluate([
            "reading /= Nothing",
            "reading |> Maybe.map routePanelShowsARoute"
            " |> Maybe.withDefault False",
            "reading |> Maybe.map routePanelSaysNoDestination"
            " |> Maybe.withDefault False",
        ], definitions=[definition])
        self.assertTrue(parsed, "the fixture did not reach the parser")
        return shows, says_none

    def test_run_31_reads_as_a_route(self):
        shows, says_none = self.answers(RUN_31_HAS_A_ROUTE)
        self.assertTrue(shows, "a five-jump route with a Current Destination "
                               "label must read as a route")
        self.assertFalse(says_none, "the stale noDestinationLabel must not "
                                    "outvote the route beside it")

    def test_run_23_reads_as_no_route(self):
        shows, says_none = self.answers(RUN_23_HAS_NO_ROUTE)
        self.assertFalse(shows)
        self.assertTrue(says_none, "the case #191 was filed on must still read "
                                   "as no route")

    def test_next_system_alone_is_not_a_route(self):
        """The discriminator. This label is in *both* captures."""
        shows, _ = self.answers([
            '<a href="showinfo:5//30002217" alt="Next System in Route">Hutian</a>',
        ])
        self.assertFalse(shows)

    def test_either_marker_alone_is_enough(self):
        destination, _ = self.answers(
            ['<a href="showinfo:5//1" alt="Current Destination">Amarr</a>'])
        jumps, _ = self.answers(["Route <fontsize=12>3 Jumps"])
        self.assertTrue(destination)
        self.assertTrue(jumps)

    def test_an_empty_panel_is_not_a_route(self):
        shows, says_none = self.answers([])
        self.assertFalse(shows)
        self.assertFalse(says_none, "an empty panel says nothing either way -- "
                                    "'no destination' is a sentence the client "
                                    "writes, not the absence of one")

    def test_the_markers_are_matched_whatever_the_casing(self):
        shows, _ = self.answers(['alt="CURRENT DESTINATION">Amarr'])
        self.assertTrue(shows)


class BothHalvesAskTheSameQuestionTest(unittest.TestCase):
    """Run 31's second defect: the decision and its own bound disagreeing.

    Read out of the source rather than executed -- `standingInADeadEnd` is a
    `let` binding inside `updateMemoryForNewReadingFromGame`, reachable only
    through a whole `UpdateMemoryContext`.
    """

    def setUp(self):
        with open(SAXRAT_BOT_ELM, encoding="utf-8") as handle:
            self.source = handle.read()

    def _dead_end(self):
        match = re.search(r"standingInADeadEnd\s*=\s*(.*?)\n\n",
                          self.source, re.S)
        self.assertIsNotNone(match, "no standingInADeadEnd binding")
        return re.sub(r"\s+", " ", match.group(1))

    def test_the_counter_reads_the_panel_the_way_the_decision_does(self):
        self.assertIn("routePanelShowsARoute", self._dead_end())

    def test_the_counter_no_longer_reads_only_the_marker_pip(self):
        """The pip is what made a real route hide the bound."""
        self.assertNotIn("currentRouteFirstMarkerRegion == Nothing",
                         self._dead_end())

    def test_the_decision_still_consults_the_words(self):
        body = body_of(self.source, "jumpToNextSystem")
        self.assertIn("routePanelSaysNoDestination", body)

    def test_one_definition_reads_the_panel_texts(self):
        """Three rules read those strings; a second copy would drift."""
        self.assertEqual(
            self.source.count("getAllContainedDisplayTexts"),
            self.source.count("getAllContainedDisplayTexts"))
        self.assertIn("routePanelTexts", self.source)
        self.assertEqual(len(re.findall(r"^routePanelTexts\s*:", self.source,
                                        re.M)), 1)


if __name__ == "__main__":
    unittest.main()
