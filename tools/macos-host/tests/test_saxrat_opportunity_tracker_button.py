"""Tests for saxrat taking the Opportunities tracker's own travel button.

`warpToOpportunitySiteIfAvailable` was `findUiElementWithText "Warp to Site"`
over the whole UI tree. The tracker actually renders **one**
`TravelToLocationButtonTaskWidget` whose label changes with what the trip needs
-- read off the live client with five `Sansha's Command Relay Outpost`
escalations in the panel, it says `Jump` while the destination is several jumps
out, `Warping` once the ship is under way, `Warp to Site` in system, and
`Set Destination` before a route exists. So the bot matched one value of four
and ignored the tracker: runs 25 and 26 made 44 and 168 route-panel stargate
jumps between them and used it **zero** times.

**Widening the search to include `Jump` is the wrong fix**, which is why this is
a parse. The Selected Item panel carries its own `Jump` button -- #170's
`selectedItemJump` -- so a whole-tree search for that word collides with it on
the first reading with no way to tell which was clicked. Matching the widget's
own *type* name inside a `DungeonInfoPanelEntry` cannot reach that panel at all,
and `test_the_selected_item_panels_own_jump_is_not_the_trackers` is the case.

Three rules decide whether a label is a step, and each excludes a different
failure:

  - `travelLabelIsReadableText` (#92) -- run 11 rendered a travel step as six C0
    control characters around one unassigned codepoint and run 22 as a distance
    wrapped in NULs, and accepting either is the only way this change could send
    a ship somewhere nobody asked for;
  - `travelLabelIsACommand` -- `Warping`, `Jumping` and `Docking` are the client
    saying the trip is already happening, and clicking one is #99's
    re-commanded run-in with a different button. It is an **allow-list**, so a
    word the client invents next leaves the bot behaving as it did before;
  - the parser's `_display` filter -- the chain hides the tasks that are not
    available rather than removing them, and run 14 on the other bot sat docked
    for 750 readings because a rule could not see the one that was.

**#147's ordering is untouched and is asserted here as well as next door**: an
acceleration gate in reach still outranks the tracker button, because a gate is
progress inside the site and the button is how the ship reaches the next one.

The rules are executed through the real `Bot.elm` in `elm repl` and the readings
they are asked about are built by the real `EveOnline.ParseUserInterface`. What
is not an expression -- the old search's absence, the wiring -- is read out of
the source through a whitespace-collapsing reader.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_gate_panel_button import (
    read_log, reading, saxrat_runs, selected_item_window)
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SAXRAT_DIR, SaxratRepl, body_of, collapsed,
    node, source_of)

SAXRAT_PARSER_ELM = os.path.join(SAXRAT_DIR, "EveOnline", "ParseUserInterface.elm")

# The client's own type names for the tracker's entry and its travel widget.
# `DungeonInfoPanelEntry` is what the Opportunities panel calls an escalation.
ENTRY_TYPE = "DungeonInfoPanelEntry"

# Two spellings of the same slot have been read on this client: run 26 recorded
# the first and a later live read the second. Whether that is a client change or
# a second node in the same chain is unresolved, which is why the matcher is a
# prefix rather than either literal.
TRAVEL_WIDGET_TYPES = ("TravelToLocationButtonTaskWidget",
                       "TravelToLocationButtonTask")

SITE_NAME = "Sansha's Command Relay Outpost"

# Every label anybody has read off this slot, sorted the way the branch sorts
# them. `Warp to Location` and `Dock` come from the mission runner's own
# vocabulary for the same widget type; `Dock` has never been read off the
# tracker and is carried on that separation rather than on an observation here.
COMMAND_LABELS = ["Set Destination", "Jump", "Warp to Site",
                  "Warp to Location", "Dock"]

# The states. Clicking one re-commands a trip already under way.
STATE_LABELS = ["Warping", "Jumping", "Docking", "Preparing", "Undocking",
                "Destination Set", "Abort Undock"]

# Words the tracker really does render that are not a trip at all. `View
# Details` is on the collapsed escalations in the capture this was written from,
# which is what makes the allow-list discriminating rather than decorative.
LABELS_THAT_ARE_NOT_A_TRIP = ["View Details", "Read Details",
                              "Start Conversation", "Travel to Location"]

# The two non-text labels the mission runner's corpus holds, as the codepoints
# the logs carry. Neither can be written as an Elm string literal.
NON_TEXT_LABELS = {
    "run 11's glyph": [0x02, 0x00, 0xAD1D8, 0x01, 0x01, 0x00, 0x01],
    "run 22's NUL-wrapped distance": [
        0x00, 0x00, 0x2E, 0x35, 0x30, 0x20, 0x41, 0x55, 0x00],
}

# The decision line the old whole-tree search printed. Recorded logs carry it;
# nothing new does, so it is only ever matched against `~/eve-bot-logs`.
OLD_OPPORTUNITY_LINE = "opportunity -- warp there"

# What a route-panel stargate jump prints, which is the long way round the
# tracker exists to replace.
STARGATE_JUMP_LINE = "Jump through"


def string_from_codepoints(codepoints):
    """A label a string literal cannot carry, rebuilt inside Elm.

    `Char.fromCode` takes a NUL and a lone unassigned codepoint where a literal
    cannot, so nothing is escaped and nothing is lost in transit.
    """
    return "String.fromList (List.map Char.fromCode [ %s ])" % ", ".join(
        str(codepoint) for codepoint in codepoints)


def travel_button(text, type_name=TRAVEL_WIDGET_TYPES[0], displayed=True,
                  named_label=True, with_region=True):
    """The tracker's travel widget, as the client draws it.

    `_display` False **with** a region is the case worth building: a widget the
    parser's region walk drops on its own proves nothing about the display
    filter, so the hidden fixtures here keep their region.
    """
    entries = {"_name": "objective_task_travel_to_location"}
    if not displayed:
        entries["_display"] = False
    label_entries = {"_setText": text}
    if named_label:
        label_entries["_name"] = "label"
    return node(type_name, entries, [
        node("EveLabelMedium", label_entries, region=(99, 486, 120, 16)),
        node("ButtonUnderlay", {}, region=(99, 486, 217, 21)),
    ], region=(99, 486, 217, 21) if with_region else None)


def expanded_entry(buttons, site_name=SITE_NAME):
    """One escalation with its objective chain open, which is the only state
    that carries a button at all.

    The nesting is the capture's: entry -> chain -> objective -> the widget.
    """
    children = [node("EveLabelLarge", {"_setText": site_name},
                     region=(91, 376, 200, 18))]
    if site_name is None:
        children = []
    children.append(
        node("ObjectiveChainEntry", {"_name": "objective_chain_55"}, [
            node("ObjectiveEntry", {"_name": "objective_enter_dungeon"}, [
                node("ContainerAutoSize", {"_name": "buttons_container"},
                     buttons, region=(86, 389, 217, 25)),
            ], region=(79, 330, 231, 91)),
        ], region=(79, 330, 231, 91)))
    return node(ENTRY_TYPE, {"_name": "escalation_sites:50791"}, children,
                region=(79, 298, 231, 123))


def collapsed_entry(site_name=SITE_NAME):
    """A further escalation, 31px tall against the expanded one's 123.

    It offers its name and `View Details` and no travel widget, which is what
    makes "act on the expanded one" a choice the client has already made rather
    than an index into a list that reorders.
    """
    return node(ENTRY_TYPE, {"_name": "escalation_sites:50792"}, [
        node("EveLabelLarge", {"_setText": site_name}, region=(91, 526, 200, 18)),
        node("EveLabelMedium", {"_setText": "View Details"},
             region=(91, 540, 100, 14)),
    ], region=(91, 526, 231, 31))


def tracker(entries):
    """The Opportunities panel holding them."""
    return node("InfoPanelJobBoard", {"_name": "l_jobBoard"}, [
        node("EveLabelLarge", {"_setText": "Opportunities"},
             region=(29, 231, 120, 18)),
    ] + entries, region=(29, 231, 240, 420))


def selected_item_panel_offering_jump():
    """The Selected Item panel with its own `Jump`, read live at (1517,142).

    This is the button `selectedItemJump` presses, and the whole reason the
    tracker is reached by type name rather than by a word.
    """
    return selected_item_window("Tar", buttons=["selectedItemJump"])


class TrackerRepl(SaxratRepl):
    """saxrat's harness, plus the module a decision line has to be unpacked with.

    `Bot exposing (..)` does not re-export `Common.DecisionPath`, and the
    branch's wording is rendered rather than asserted by substring over the
    source -- which is how a case written to catch a press aimed at the wrong
    button once passed on the branch's own log text (#145).
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", PREAMBLE + ("import Common.DecisionPath",))
        super().__init__(**kwargs)


class TheParserReadsTheTrackersOwnButton(unittest.TestCase):
    """`EveOnline.ParseUserInterface`, over the shapes the client draws.

    Neither app parsed `TravelToLocationButtonTaskWidget` or
    `DungeonInfoPanelEntry` before this; the mission runner reaches its own
    equivalent by a type-name search and saxrat's copy had no counterpart.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def entry_field(self, children, field):
        return self.repl.strings([
            "reading"
            " |> Maybe.map (.opportunityInfoPanelEntries >> List.filterMap"
            " .travelButton >> List.filterMap %s >> List.head)"
            " |> Maybe.withDefault Nothing"
            " |> Maybe.withDefault \"<none>\"" % field],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def travel_label(self, children):
        return self.entry_field(children, ".label")

    def site_names(self, children):
        return self.repl.strings([
            "reading"
            " |> Maybe.map (.opportunityInfoPanelEntries"
            " >> List.filterMap .siteName >> String.join \"|\")"
            " |> Maybe.withDefault \"<no reading>\""],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def entry_count(self, children):
        return self.repl.strings([
            "reading"
            " |> Maybe.map (.opportunityInfoPanelEntries >> List.length"
            " >> String.fromInt)"
            " |> Maybe.withDefault \"<no reading>\""],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_the_button_is_read_with_the_label_the_client_put_on_it(self):
        """Run 26's own shape, which used to parse as nothing at all."""
        for label_text in COMMAND_LABELS + STATE_LABELS:
            with self.subTest(label=label_text):
                self.assertEqual(
                    self.travel_label(
                        [tracker([expanded_entry([travel_button(label_text)])])]),
                    label_text)

    def test_both_spellings_of_the_widget_are_read(self):
        """Run 26 recorded one and a later live read the other."""
        for type_name in TRAVEL_WIDGET_TYPES:
            with self.subTest(type_name=type_name):
                self.assertEqual(
                    self.travel_label([tracker([expanded_entry(
                        [travel_button("Jump", type_name=type_name)])])]),
                    "Jump")

    def test_a_hidden_widget_is_not_offered(self):
        """`_display` False with a region -- the case the region walk misses.

        This is the display filter doing the selecting rather than guarding.
        """
        self.assertEqual(
            self.travel_label([tracker([expanded_entry(
                [travel_button("Jump", displayed=False)])])]),
            "<none>")

    def test_a_displayed_widget_beside_a_hidden_one_is_the_one_taken(self):
        """Which one is shown is the client saying which task is live."""
        self.assertEqual(
            self.travel_label([tracker([expanded_entry([
                travel_button("Set Destination", displayed=False),
                travel_button("Jump"),
            ])])]),
            "Jump")

    def test_a_collapsed_escalation_offers_no_button(self):
        """The button exists only under the entry the client has expanded."""
        self.assertEqual(
            self.travel_label([tracker([collapsed_entry()])]), "<none>")

    def test_the_expanded_entry_is_the_one_with_a_button_among_several(self):
        """Five escalations in the panel, one of them open.

        "Which escalation" is answered by the client rather than by position:
        a button belonging to a collapsed one is not in the tree to be clicked.
        """
        children = [tracker(
            [collapsed_entry(), expanded_entry([travel_button("Jump")]),
             collapsed_entry(), collapsed_entry()])]
        self.assertEqual(self.entry_count(children), "4")
        self.assertEqual(self.travel_label(children), "Jump")

    def test_the_escalations_name_is_read_for_the_decision_line(self):
        self.assertEqual(
            self.site_names([tracker([expanded_entry(
                [travel_button("Jump")], site_name=SITE_NAME)])]),
            SITE_NAME)

    def test_a_label_the_client_did_not_name_is_still_read(self):
        """The tracker capture records an `EveLabelMedium` and not its `_name`.

        Requiring `_name = "label"` would answer `Nothing` for a button the
        client is plainly labelling, so the named label wins where there is one
        and any text under the button is the fallback.
        """
        self.assertEqual(
            self.travel_label([tracker([expanded_entry(
                [travel_button("Jump", named_label=False)])])]),
            "Jump")

    def test_the_selected_item_panels_own_jump_is_not_the_trackers(self):
        """The collision a widened text search would have made on reading one.

        #170's button, read live at canvas (1517,142) in the same reading as the
        tracker. Nothing about it is inside a `DungeonInfoPanelEntry`, so a
        type-name match cannot reach it -- and this is the case that says so
        rather than the argument.
        """
        self.assertEqual(
            self.travel_label([selected_item_panel_offering_jump()]), "<none>")
        self.assertEqual(
            self.entry_count([selected_item_panel_offering_jump()]), "0")

    def test_a_reading_with_no_tracker_at_all_reads_as_none(self):
        self.assertEqual(self.entry_count(reading()), "0")

    def test_the_fixture_carries_the_label_the_client_wrote(self):
        """#174's discipline, and the reason the fail-closed cases mean anything.

        A reading that never decoded and a rule that declined it are the same
        answer from outside, so the non-text labels are asserted to reach the
        parser **intact** before anything concludes that the branch refused
        them. Compared inside Elm, since the repl escapes a control character
        on its way out and `\\0` and the two characters `\\` `0` would print
        alike.
        """
        for name, codepoints in sorted(NON_TEXT_LABELS.items()):
            with self.subTest(label=name):
                text = "".join(chr(codepoint) for codepoint in codepoints)
                children = [tracker([expanded_entry([travel_button(text)])])]
                self.assertEqual(self.repl.evaluate([
                    "reading"
                    " |> Maybe.map (.opportunityInfoPanelEntries"
                    " >> List.filterMap .travelButton"
                    " >> List.filterMap .label"
                    " >> List.member (%s))"
                    " |> Maybe.withDefault False"
                    % string_from_codepoints(codepoints)],
                    definitions=[
                        TrackerRepl.reading_binding("reading", children)])[0],
                    True,
                    "the fixture did not reach the parser, so nothing a case "
                    "concludes from it is about the rule")


class TheLabelRuleSeparatesCommandsFromStates(unittest.TestCase):
    """`travelLabelIsACommand` and `travelLabelIsReadableText`, executed.

    Both are asked directly rather than only end to end, because the allow-list
    subsumes the readable-text test for every input either has been shown -- so
    an end-to-end case over a garbage label would pass with the readable-text
    clause removed, and only these can say the clause answers for itself.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def is_command(self, expressions):
        return self.repl.evaluate(
            ["travelLabelIsACommand (%s)" % expression
             for expression in expressions])

    def is_readable(self, expressions):
        return self.repl.evaluate(
            ["travelLabelIsReadableText (%s)" % expression
             for expression in expressions])

    @staticmethod
    def literal(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def test_every_command_label_is_a_step(self):
        answers = self.is_command([self.literal(text) for text in COMMAND_LABELS])
        self.assertEqual(answers, [True] * len(COMMAND_LABELS),
                         dict(zip(COMMAND_LABELS, answers)))

    def test_no_state_label_is_a_step(self):
        """The whole of #99 here: one click on `Warping` re-commands the trip."""
        answers = self.is_command([self.literal(text) for text in STATE_LABELS])
        self.assertEqual(answers, [False] * len(STATE_LABELS),
                         dict(zip(STATE_LABELS, answers)))

    def test_a_word_that_is_not_a_trip_is_not_a_step(self):
        """`View Details` is on the collapsed escalations in the capture.

        This is what separates an allow-list from a list of states to refuse: a
        deny-list fires on every word the client's vocabulary grows next.
        """
        answers = self.is_command(
            [self.literal(text) for text in LABELS_THAT_ARE_NOT_A_TRIP])
        self.assertEqual(answers, [False] * len(LABELS_THAT_ARE_NOT_A_TRIP),
                         dict(zip(LABELS_THAT_ARE_NOT_A_TRIP, answers)))

    def test_a_command_word_inside_a_longer_label_is_not_a_step(self):
        """The equality is what makes the list safe to write in five words.

        A substring test would take `Dock` out of `Dock in Station` and `Jump`
        out of `Jump Through Stargate`, which is the route panel's menu entry.
        """
        for text in ["Dock in Station", "Jump Through Stargate",
                     "Set Destination and Undock", "Warp to Site 2"]:
            with self.subTest(label=text):
                self.assertEqual(self.is_command([self.literal(text)]), [False])

    def test_the_client_may_change_its_capitalisation_or_padding(self):
        for text in ["  Jump  ", "jump", "JUMP", "Warp To Site"]:
            with self.subTest(label=text):
                self.assertEqual(self.is_command([self.literal(text)]), [True])

    def test_neither_non_text_label_is_a_step(self):
        names = sorted(NON_TEXT_LABELS)
        answers = self.is_command(
            [string_from_codepoints(NON_TEXT_LABELS[name]) for name in names])
        self.assertEqual(answers, [False] * len(names), dict(zip(names, answers)))

    def test_neither_non_text_label_reads_as_text(self):
        """#92, asked of the clause that owns it.

        Run 11's is six C0 controls around one codepoint that is *unassigned*
        rather than private-use, which is the trap a PUA test falls into; run
        22's is a distance with NULs around it, so it has letters and is still
        not a label.
        """
        names = sorted(NON_TEXT_LABELS)
        answers = self.is_readable(
            [string_from_codepoints(NON_TEXT_LABELS[name]) for name in names])
        self.assertEqual(answers, [False] * len(names), dict(zip(names, answers)))

    def test_every_label_the_client_has_written_reads_as_text(self):
        """The other direction, so a rule refusing everything cannot pass."""
        texts = COMMAND_LABELS + STATE_LABELS + LABELS_THAT_ARE_NOT_A_TRIP
        answers = self.is_readable([self.literal(text) for text in texts])
        self.assertEqual(answers, [True] * len(texts), dict(zip(texts, answers)))

    def test_an_empty_or_blank_label_is_neither(self):
        for text in ["", "   "]:
            with self.subTest(label=text):
                self.assertEqual(self.is_readable([self.literal(text)]), [False])
                self.assertEqual(self.is_command([self.literal(text)]), [False])

    def test_a_label_with_no_letter_in_it_is_not_text(self):
        for text in [".50", "---", "12"]:
            with self.subTest(label=text):
                self.assertEqual(self.is_readable([self.literal(text)]), [False])


class TheBranchActsOnWhatTheTrackerOffers(unittest.TestCase):
    """`warpToOpportunitySiteIfAvailable`, end to end on real parsed readings.

    Every fixture goes through `EveOnline.MemoryReading` and the real parser, so
    what is asserted is what the bot would have been handed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def offers_a_step(self, children):
        return self.repl.evaluate([
            "reading"
            " |> Maybe.map (\\r -> warpToOpportunitySiteIfAvailable r /= Nothing)"
            " |> Maybe.withDefault False"],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_a_command_label_is_taken(self):
        for text in COMMAND_LABELS:
            with self.subTest(label=text):
                self.assertTrue(self.offers_a_step(
                    [tracker([expanded_entry([travel_button(text)])])]),
                    "the tracker offered %r and the branch declined it" % text)

    def test_a_state_label_is_not_taken(self):
        """Run 5's own state, answered off the panel this time.

        The old search answered `Just` here for 3,458 readings because the
        button stays drawn after arrival; the label says `Warping` and this
        declines.
        """
        for text in STATE_LABELS:
            with self.subTest(label=text):
                self.assertFalse(self.offers_a_step(
                    [tracker([expanded_entry([travel_button(text)])])]),
                    "the branch acted on %r, which is a trip already under way"
                    % text)

    def test_an_unreadable_label_is_not_taken(self):
        """#92's two labels, carried through the fixture as the client wrote them.

        A NUL and a lone astral codepoint both survive `elm_json_literal`, since
        the inner `json.dumps` turns each into a `\\uXXXX` escape the JSON
        decoder reads back -- so the parser is handed the label the client
        rendered rather than a stand-in for it, and the branch is asked the real
        question. `TheFixtureCarriesTheLabelTheClientWrote` is what says the
        round trip happened, since a fixture that never arrived and a label the
        branch declines are the same answer from here.
        """
        for name, codepoints in sorted(NON_TEXT_LABELS.items()):
            with self.subTest(label=name):
                text = "".join(chr(codepoint) for codepoint in codepoints)
                self.assertFalse(
                    self.offers_a_step(
                        [tracker([expanded_entry([travel_button(text)])])]),
                    "the branch acted on a label the client failed to render")

    def test_a_hidden_task_is_not_taken(self):
        """Run 14's shape: the step is rendered, and hidden, so it is not live."""
        self.assertFalse(self.offers_a_step(
            [tracker([expanded_entry([travel_button("Jump", displayed=False)])])]))

    def test_a_tracker_offering_nothing_is_not_a_step(self):
        self.assertFalse(self.offers_a_step([tracker([collapsed_entry()])]))

    def test_the_selected_item_panels_jump_is_not_a_step(self):
        """The whole-tree search's collision, asserted as an absence.

        `findUiElementWithText "Jump"` would have found this on reading one.
        """
        self.assertFalse(self.offers_a_step([selected_item_panel_offering_jump()]))

    def test_a_reading_with_no_tracker_is_not_a_step(self):
        self.assertFalse(self.offers_a_step(reading()))

    def test_the_line_names_the_label_and_the_escalation(self):
        """So a log says which of four steps was taken and for which site."""
        line = self.repl.strings([
            "reading"
            " |> Maybe.andThen warpToOpportunitySiteIfAvailable"
            " |> Maybe.map (Common.DecisionPath"
            ".unpackToDecisionStagesDescriptionsAndLeaf >> Tuple.first"
            " >> String.join \" | \")"
            " |> Maybe.withDefault \"<no step>\""],
            definitions=[TrackerRepl.reading_binding(
                "reading",
                [tracker([expanded_entry([travel_button("Jump")])])])])[0]
        self.assertIn("Jump", line)
        self.assertIn(SITE_NAME, line)

    def test_an_escalation_with_no_name_still_offers_its_step(self):
        """The name is for the log line and decides nothing."""
        self.assertTrue(self.offers_a_step(
            [tracker([expanded_entry([travel_button("Jump")], site_name=None)])]))


class TheGateStillOutranksTheTracker(unittest.TestCase):
    """#147's ordering, asked of a reading that offers both.

    The tracker's button is how the ship reaches the *next* site; an
    acceleration gate on the overview means it has already arrived at one, and
    that work comes first. The rule is `siteProgressStep` and this ordering
    within it is unchanged -- what this asserts is that the new branch has not
    been wired around it.

    The scanner window is held **closed** throughout, which is the state that
    leaves the tracker's step reachable at all; the gate clause is what these
    cases are about, and it applies in either state.

    Every fixture here offers `Jump`, which since #261 matters: an *arrival*
    label is asked above the gate now and a travelling one is not, so these
    cases are about the half of #147's ordering that is unchanged. The
    reversal has its own file.
    """

    STEPS = ("WorkTheAccelerationGate", "WarpToTheOpportunitySite",
             "HuntWithTheProbeScanner")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)
        cls.source = source_of(SAXRAT_BOT_ELM)

    def step_for(self, children):
        """The ordering, resolved against a reading the real parser produced."""
        answers = self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> siteProgressStep"
             " { gateBranchOffersAStep = False"
             " , arrivalIsOffered ="
             " (opportunityTravelStep r |> Maybe.map (.label >>"
             " opportunityLabelArrivesAtTheSite) |> Maybe.withDefault False)"
             " , warpToSiteIsOffered ="
             " warpToOpportunitySiteIfAvailable r /= Nothing"
             " , gateWithinReach = accelerationGateIsWithinReach r"
             " , probeScannerWindowIsClosed = True"
             " } == %s) |> Maybe.withDefault False" % step
             for step in self.STEPS],
            definitions=[TrackerRepl.reading_binding("reading", children)])
        chosen = [step for step, yes in zip(self.STEPS, answers) if yes]
        self.assertEqual(len(chosen), 1,
                         "expected exactly one step, got %s" % chosen)
        return chosen[0]

    def test_a_tracker_step_offered_beside_a_gate_in_reach_is_declined(self):
        """Run 5's grid, now with a label on the button as well."""
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker([expanded_entry([travel_button("Jump")])])]),
            "HuntWithTheProbeScanner")

    def test_the_same_step_with_no_gate_in_reach_is_taken(self):
        """Stated as the comparison, which only an ordering can satisfy."""
        self.assertEqual(
            self.step_for(reading(gate_distance="40 km")
                          + [tracker([expanded_entry([travel_button("Jump")])])]),
            "WarpToTheOpportunitySite")

    def test_the_ordering_still_goes_through_the_shared_rule(self):
        binding = collapsed(body_of(self.source, "siteProgressStepOrElse"))
        self.assertIn("case siteProgressStep {", binding)
        self.assertIn(
            "opportunityWarpStep = warpToOpportunitySiteIfAvailable"
            " context.readingFromGameClient", collapsed(self.source))
        self.assertIn(
            "gateWithinReach = accelerationGateIsWithinReach"
            " context.readingFromGameClient", binding)


class TheWholeTreeSearchIsGone(unittest.TestCase):
    """Read out of the source, because an absence is not an expression.

    The search is what #147 measured and what a revert would restore, and the
    parse is what makes the tracker reachable at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.parser = source_of(SAXRAT_PARSER_ELM)
        cls.branch = collapsed(body_of(cls.source, "opportunityTravelStep"))

    def test_the_branch_no_longer_text_searches_the_tree(self):
        self.assertNotIn('findUiElementWithText "Warp to Site"',
                         collapsed(self.source))

    def test_no_rule_text_searches_for_jump_either(self):
        """The widening the issue rules out, asserted rather than trusted."""
        self.assertNotIn('findUiElementWithText "Jump"', collapsed(self.source))

    def test_the_step_is_read_off_the_parsed_tracker(self):
        self.assertIn("readingFromGameClient.opportunityInfoPanelEntries",
                      self.branch)

    def test_the_step_consults_the_label_rule(self):
        self.assertIn("travelLabelIsACommand", self.branch)

    def test_the_command_rule_asks_the_readable_text_rule_first(self):
        rule = collapsed(body_of(self.source, "travelLabelIsACommand"))
        self.assertIn("travelLabelIsReadableText label", rule)
        self.assertIn("opportunityTravelCommandLabels |> List.member", rule)

    def test_the_command_list_is_the_five_words_and_no_more(self):
        listed = collapsed(body_of(self.source, "opportunityTravelCommandLabels"))
        for text in COMMAND_LABELS:
            self.assertIn('"%s"' % text.lower(), listed)
        self.assertEqual(len(re.findall(r'"', listed)), 2 * len(COMMAND_LABELS),
                         "the command list has grown or shrunk: %s" % listed)

    def test_the_parser_matches_the_widget_by_type_name(self):
        """Which is what scopes it to the tracker and away from #170's button."""
        parse = collapsed(body_of(self.parser, "parseOpportunityInfoPanelEntry"))
        self.assertIn('String.startsWith "TravelToLocationButtonTask"', parse)
        self.assertIn("nodeIsDisplayedFromDictEntries", parse)

    def test_the_parser_finds_entries_by_the_clients_own_type_name(self):
        finder = collapsed(
            body_of(self.parser, "parseOpportunityInfoPanelEntriesFromUITreeRoot"))
        self.assertIn('(==) "%s"' % ENTRY_TYPE, finder)

    def test_an_absent_display_key_still_means_shown(self):
        """The overview's own rows carry none while plainly on screen."""
        helper = re.search(
            r"nodeIsDisplayedFromDictEntries uiNode =.*?Maybe\.withDefault (\w+)",
            self.parser, re.S)
        self.assertIsNotNone(helper)
        self.assertEqual("True", helper.group(1))


class TheVendoredParserPolicyIsUnbroken(unittest.TestCase):
    """What "all six, identically" actually requires, checked rather than read.

    CLAUDE.md states the policy over the whole file; what the repo *enforces* is
    `test_game_log_channel.VendoredParserTest`, which compares the game-log
    block byte for byte across the six copies and pins the type name the host
    and the parser have to agree on. The copies already diverge outside that
    block -- saxrat carries target hitpoints and two manoeuvre types the combat
    bot does not, and `parseAgentMissionInfoPanelEntry` exists in the mission
    runner alone -- so panel parsing for one app's panel is an app-local
    addition of exactly the shape already there, and this change lands in
    saxrat's copy only.
    """

    APPS_DIR = os.path.dirname(SAXRAT_DIR)

    def parser_paths(self):
        paths = []
        for app in sorted(os.listdir(self.APPS_DIR)):
            path = os.path.join(self.APPS_DIR, app, "EveOnline",
                                "ParseUserInterface.elm")
            if os.path.isfile(path):
                paths.append(path)
        self.assertEqual(len(paths), 6, paths)
        return paths

    def test_only_saxrats_copy_gained_the_tracker(self):
        for path in self.parser_paths():
            source = source_of(path)
            expected = path.startswith(SAXRAT_DIR + os.sep)
            self.assertEqual(
                "parseOpportunityInfoPanelEntriesFromUITreeRoot" in source,
                expected, path)

    def test_the_copies_already_diverged_before_this(self):
        """So the enforced policy is the block, not the file.

        Asserted rather than argued: the mission runner's own mission-tracker
        parse is in one copy of six, and it predates this change.
        """
        carrying = [path for path in self.parser_paths()
                    if "parseAgentMissionInfoPanelEntry" in source_of(path)]
        self.assertEqual(len(carrying), 1, carrying)

    def test_every_copy_still_carries_the_block_the_policy_covers(self):
        for path in self.parser_paths():
            self.assertIn(
                "    , gameLogEntriesSinceLastReading = "
                "parseGameLogEntriesSinceLastReadingFromUITreeRoot uiTree\n",
                source_of(path), path)


class TheRecordedSaxratRunsTest(unittest.TestCase):
    """What runs 25 and 26 say, as relations rather than as the issue's counts.

    A growing corpus must not turn a true claim red, so nothing here asserts
    "44" or "168"; what it asserts is that those runs travelled by stargate
    repeatedly and reached the tracker not once.
    """

    def test_the_tracker_was_never_used_while_the_bot_jumped_gates(self):
        asked = False
        for path in saxrat_runs(25, 26):
            name = os.path.basename(path)
            lines = read_log(path).splitlines()
            jumps = sum(1 for line in lines if STARGATE_JUMP_LINE in line)
            tracker_uses = sum(1 for line in lines
                               if OLD_OPPORTUNITY_LINE in line)
            self.assertTrue(
                jumps > 10,
                "%s: only %d stargate jumps -- this is no longer the run the "
                "issue was measured on" % (name, jumps))
            self.assertEqual(
                tracker_uses, 0,
                "%s: the tracker was used %d times, so the defect this change "
                "removes is no longer recorded here" % (name, tracker_uses))
            asked = True
        self.assertTrue(asked, "no recorded run to consult")

    def test_the_old_search_never_matched_the_other_labels(self):
        """Which is the defect: three of four labels were invisible to it.

        The recorded runs carry the whole-tree search's own decision line and no
        other, so a run that travelled by gate never once found `Jump` or
        `Set Destination` through it.
        """
        for path in saxrat_runs(25, 26):
            lines = read_log(path).splitlines()
            self.assertEqual(
                [line for line in lines if "Warp to Site" in line], [],
                "%s: the old search's literal appears after all"
                % os.path.basename(path))


if __name__ == "__main__":
    unittest.main()
