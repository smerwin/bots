"""Tests for arriving at an escalation rather than travelling past it (#254).

`opportunityTravelStep` ended in `List.head`, which with several escalations
open is not a choice at all -- it takes whichever entry the panel lists first.

Run 38 is what that cost. The Opportunities panel held three
`Sansha's Command Relay Outpost` entries; the ship reached the system holding
one of them, where that entry offers `Warp to Site`; and the branch pressed the
*first* entry's `Jump` instead. Over three hours it pressed `Jump` 1,989 times
and `Set Destination` 257, **never once warped to a site**, crossed from Domain
into Kor-Azor, and visited two anomalies. Run 37, on the same settings with no
escalation on offer, visited 21.

The ordering is between the two kinds of label rather than between entries: a
warp or a dock is the ship arriving at a site it is already in the system for,
where `jump` and `set destination` are it leaving for another one.

It is a **preference and not a filter** -- with nothing arriving on offer the
answer is the first travelling step, exactly as before -- which is the case a
mutation is most likely to break silently.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import SAXRAT_BOT_ELM, body_of
from test_saxrat_opportunity_tracker_button import (
    TrackerRepl, expanded_entry, tracker, travel_button)


def entry_offering(label, name="escalation_sites:50791"):
    """One expanded escalation whose travel widget offers `label`."""
    entry = expanded_entry([travel_button(label)])
    entry["dictEntriesOfInterest"]["_name"] = name
    return entry


class ArrivingBeatsTravellingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def chosen(self, labels):
        """The label the branch would press, for a panel offering `labels`."""
        entries = [entry_offering(text, "escalation_sites:%d" % (50791 + index))
                   for index, text in enumerate(labels)]
        binding = self.repl.reading_binding("reading", [tracker(entries)])
        count, chosen = self.repl.strings([
            'reading |> Maybe.map (.opportunityInfoPanelEntries >> List.length'
            ' >> String.fromInt) |> Maybe.withDefault "NO READING"',
            'reading |> Maybe.andThen opportunityTravelStep'
            ' |> Maybe.map .label |> Maybe.withDefault "nothing"',
        ], definitions=[binding])
        self.assertEqual(count, str(len(labels)),
                         "the fixture did not reach the parser as %d entries "
                         "(got %r) -- a case over a reading that never arrived "
                         "proves nothing" % (len(labels), count))
        return chosen

    def test_run_38s_panel_warps_instead_of_jumping(self):
        """Three outposts, the reachable one second. This is the incident."""
        self.assertEqual(
            self.chosen(["Jump", "Warp to Site", "Jump"]), "Warp to Site")

    def test_it_does_not_depend_on_position(self):
        self.assertEqual(
            self.chosen(["Warp to Site", "Jump"]), "Warp to Site")
        self.assertEqual(
            self.chosen(["Set Destination", "Jump", "Warp to Site"]),
            "Warp to Site")

    def test_travelling_is_still_taken_when_nothing_arrives(self):
        """The preference must not become a filter: a single distant
        escalation has to behave exactly as it does today."""
        self.assertEqual(self.chosen(["Jump"]), "Jump")
        self.assertEqual(self.chosen(["Set Destination"]), "Set Destination")
        self.assertEqual(
            self.chosen(["Set Destination", "Jump"]), "Set Destination")

    def test_dock_and_warp_to_location_also_arrive(self):
        self.assertEqual(self.chosen(["Jump", "Dock"]), "Dock")
        self.assertEqual(
            self.chosen(["Jump", "Warp to Location"]), "Warp to Location")

    def test_casing_and_spacing_do_not_decide_it(self):
        self.assertEqual(
            self.chosen(["Jump", "  warp to site  "]).strip(), "warp to site")

    def test_a_state_label_is_still_not_a_step(self):
        """`Warping` is the client saying the trip is already under way, and
        pressing it re-commands a manoeuvre -- #99's docking run-in again."""
        self.assertEqual(self.chosen(["Warping"]), "nothing")

    def test_a_state_label_does_not_outrank_a_real_command(self):
        self.assertEqual(self.chosen(["Warping", "Jump"]), "Jump")


class TheArrivalLabelsAreASubsetTest(unittest.TestCase):
    """Every arrival label must also be a command label, or the preference
    names something the filter above it has already dropped."""

    def setUp(self):
        with open(SAXRAT_BOT_ELM, encoding="utf-8") as handle:
            self.source = handle.read()

    def _labels(self, name):
        body = body_of(self.source, name)
        return set(re.findall(r'"([^"]+)"', body))

    def test_arrival_labels_are_all_command_labels(self):
        arrival = self._labels("opportunityArrivalCommandLabels")
        command = self._labels("opportunityTravelCommandLabels")
        self.assertTrue(arrival, "no arrival labels found")
        self.assertTrue(arrival <= command,
                        "%s is not offered by the command filter"
                        % (arrival - command))

    def test_the_travelling_verbs_are_not_arrival_labels(self):
        arrival = self._labels("opportunityArrivalCommandLabels")
        self.assertNotIn("jump", arrival)
        self.assertNotIn("set destination", arrival)

    def test_the_step_no_longer_takes_whichever_is_first(self):
        body = body_of(self.source, "opportunityTravelStep")
        self.assertIn("opportunityStepArrivingFirst", body)


if __name__ == "__main__":
    unittest.main()
