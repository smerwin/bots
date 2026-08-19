"""Tests for a same-system escalation step surviving the destination filter.

Run 6 tracked five `Sansha's Command Relay Outpost` entries and could act on
**none** of them, at any step, for the whole session. The docked branch's
`warpToOpportunitySiteIfAvailable == Nothing` check never saw a reason to
undock; once undocked by another route entirely, the next step -- `Warp to
Site`, a real command label -- still could not be reached.

**The cause is `escalationDestinationIsPermitted`, and it is not the label.**
The tracker's own progress bar (`8 jumps | 0.6 Andabiar` in #291's capture) is
what `parseOpportunityDestination` reads a destination system and its security
off of. A step that never leaves the current system draws no such bar, so
`entry.destination` parses as `Just { jumps = Nothing, security = Nothing,
systemName = Nothing }` -- captured live, off saxrat run 6, docked at Nafomeh
with the tracker reading `Undock` -- and the strict rule this function used to
be, `entry.destination |> Maybe.andThen .security |> securityIsPermitted ...`,
refuses an absent security exactly as hard as it refuses one the client named a
system for and would not say. Every entry, every reading, every step, for the
whole session.

**The fix does not touch `securityIsPermitted` or the case that rule exists
for.** A step that *does* name a remote system is still refused unless that
system's security is known and high enough --
`TheEscalationDestinationIsReadAndBoundedTest` in
`test_saxrat_opportunity_tracker_button.py` already covers that rule directly
and continues to. What changes is only the case a real remote destination and a
merely local one used to share: no system named at all.

Confirmed against the live client before this file existed: decoding run 6's
own captured UI tree through the real parser and the pre-fix
`escalationDestinationIsPermitted` filtered its tracked entry out
(`permitted = []`), and `opportunityTravelStep` answered `Nothing` on a panel
plainly offering `Undock`. The post-fix build answered
`Just { label = "Undock", siteName = Just "Sansha's Command Relay Outpost", ... }`
against the same captured reading, and the fixed bot undocked, warped to the
site and started killing rats within the next few readings of a live run.

The second, independent gap this run exposed: `opportunityTravelCommandLabels`
never carried `"undock"`, so even a step that had survived the destination
filter would have been declined as an unrecognised word. Both had to be fixed
together to reach the working state above -- see
`TheUndockLabelIsRecognisedTest`.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import SAXRAT_BOT_ELM, body_of, collapsed, source_of
from test_saxrat_opportunity_tracker_button import (
    TrackerRepl, expanded_entry, progress_bar, tracker, travel_button)


class LocalEscalationStepIsPermittedTest(unittest.TestCase):
    """The regression this file exists for, and the guard against overcorrecting."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def chosen(self, entries):
        """The label taken, for a panel holding these entries, after the same
        narrowing every real call site applies.

        Mirrors `ArrivingBeatsTravellingTest.chosen` in the neighbouring file:
        the fixture's own entry count is asserted first, because a case over a
        reading that never arrived passes for the wrong reason.
        """
        binding = self.repl.reading_binding("reading", [tracker(entries)])
        raw_count, permitted_count, chosen = self.repl.strings([
            'reading |> Maybe.map (.opportunityInfoPanelEntries >> List.length'
            ' >> String.fromInt) |> Maybe.withDefault "NO READING"',
            'reading |> Maybe.map (escalationEntriesPermitted defaultBotSettings'
            ' >> .opportunityInfoPanelEntries >> List.length >> String.fromInt)'
            ' |> Maybe.withDefault "NO READING"',
            'reading |> Maybe.map (escalationEntriesPermitted defaultBotSettings)'
            ' |> Maybe.andThen opportunityTravelStep'
            ' |> Maybe.map .label |> Maybe.withDefault "nothing"',
        ], definitions=[binding])
        self.assertEqual(
            raw_count, str(len(entries)),
            "the fixture did not reach the parser as %d entries (got %r) -- a "
            "case over a reading that never arrived proves nothing"
            % (len(entries), raw_count))
        return permitted_count, chosen

    def test_an_undock_step_with_no_destination_survives_the_filter(self):
        """Run 6's own shape: one entry, an Undock button, no progress bar."""
        permitted, label = self.chosen([expanded_entry([travel_button("Undock")])])
        self.assertEqual(permitted, "1")
        self.assertEqual(label, "Undock")

    def test_a_warp_to_site_step_with_no_destination_survives_the_filter(self):
        """What run 6's tracker offered one step later, once undocked."""
        permitted, label = self.chosen(
            [expanded_entry([travel_button("Warp to Site")])])
        self.assertEqual(permitted, "1")
        self.assertEqual(label, "Warp to Site")

    def test_an_unrecognised_label_with_no_destination_is_still_declined(self):
        """The fix widens which entries reach the label check. It must not
        also widen the label check -- `View Details` on a same-system entry
        must decline exactly as it does on a queued one."""
        permitted, label = self.chosen(
            [expanded_entry([travel_button("View Details")])])
        self.assertEqual(permitted, "1",
                         "the entry should still pass the destination filter")
        self.assertEqual(label, "nothing",
                         "an unrecognised label must still be declined")

    def test_a_remote_escalation_with_low_security_is_still_refused(self):
        """The regression guard: a step that *does* name a system is exactly
        as refused as it was before this fix. #291's own shape."""
        permitted, label = self.chosen([
            expanded_entry([travel_button("Jump"), progress_bar(
                jumps="8 jumps", destination="0.3 Arodan")]),
        ])
        self.assertEqual(permitted, "0",
                         "a named lowsec-adjacent destination must still be "
                         "filtered out")
        self.assertEqual(label, "nothing")

    def test_a_remote_escalation_with_permitted_security_still_survives(self):
        """And the other side of that line still works, unaffected."""
        permitted, label = self.chosen([
            expanded_entry([travel_button("Jump"), progress_bar(
                jumps="8 jumps", destination="0.9 SafeSystem")]),
        ])
        self.assertEqual(permitted, "1")
        self.assertEqual(label, "Jump")

    def test_a_mix_of_local_and_remote_entries(self):
        """The realistic run-6 shape: several queued outposts (no travel
        widget at all, so #291's own machinery already excludes them) beside
        the one the tracker is actually working."""
        permitted, label = self.chosen([
            expanded_entry([travel_button("Jump"), progress_bar(
                jumps="14 jumps", destination="0.2 Elsewhere")],
                site_name="Sansha's Command Relay Outpost"),
            expanded_entry([travel_button("Undock")],
                site_name="Sansha's Command Relay Outpost"),
        ])
        self.assertEqual(permitted, "1",
                         "only the local, no-destination entry should survive")
        self.assertEqual(label, "Undock")


class TheUndockLabelIsRecognisedTest(unittest.TestCase):
    """The second, independent half of run 6's bug.

    Neither gap alone explains what was observed: the destination filter was
    what kept the tracker invisible the whole session, but even a build
    carrying only that fix would still decline an `Undock` step on the label
    check -- the docked branch would still never see a reason to leave.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_undock_is_a_command(self):
        self.assertEqual(
            self.repl.strings(['Debug.toString (travelLabelIsACommand "Undock")'])[0],
            "True")

    def test_undock_is_not_an_arrival(self):
        """Undocking does not arrive at a site -- it is a prerequisite for
        reaching one, the same shape as `Jump` and `Set Destination`. Confirmed
        rather than assumed: `opportunityStepArrivingFirst` must not prefer it
        over a genuine `Warp to Site` sitting in the same panel."""
        self.assertEqual(
            self.repl.strings(['Debug.toString (opportunityLabelArrivesAtTheSite "Undock")'])[0],
            "False")

    def test_undock_does_not_outrank_a_real_arrival(self):
        binding = self.repl.reading_binding("reading", [tracker([
            expanded_entry([travel_button("Undock")],
                site_name="Sansha's Command Relay Outpost"),
        ])])
        # A single-entry panel cannot show both in one fixture -- what matters
        # here is that Undock's own arrival answer does not flip the ordering
        # rule tested directly above. The end-to-end preference between the two
        # is `ArrivingBeatsTravellingTest`'s territory in the neighbouring file.
        label = self.repl.strings([
            'reading |> Maybe.map (escalationEntriesPermitted defaultBotSettings)'
            ' |> Maybe.andThen opportunityTravelStep'
            ' |> Maybe.map .label |> Maybe.withDefault "nothing"',
        ], definitions=[binding])[0]
        self.assertEqual(label, "Undock")


class TheFixIsScopedToAnAbsentSystemNameTest(unittest.TestCase):
    """Read out of the source, so a later edit that widens either fix past
    what run 6 needed has to argue against a case rather than drift past one
    unnoticed."""

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.collapsed = collapsed(self.source)

    def test_the_permission_still_branches_on_the_system_name(self):
        body = body_of(self.source, "escalationDestinationIsPermitted")
        self.assertIn("systemName", body,
                      "the fix should branch on whether a system was named, "
                      "not drop the safety check outright")

    def test_a_named_destination_still_reaches_securityIsPermitted(self):
        """The one branch #291 was written to protect must still exist:
        naming a system and refusing to say how safe it is must still refuse
        the trip. `TheEscalationDestinationIsReadAndBoundedTest` covers
        `securityIsPermitted` itself directly; this only guards that
        `escalationDestinationIsPermitted` still calls it somewhere."""
        body = body_of(self.source, "escalationDestinationIsPermitted")
        self.assertIn("securityIsPermitted", body)

    def test_undock_is_in_the_command_labels(self):
        body = body_of(self.source, "opportunityTravelCommandLabels")
        self.assertIn('"undock"', body)

    def test_undock_is_not_in_the_arrival_labels(self):
        """Undock reaching the arrival list would let it outrank a real
        `Warp to Site` offered in the same panel -- #254's own defect, in the
        opposite direction, over the label this run added."""
        body = body_of(self.source, "opportunityArrivalCommandLabels")
        self.assertNotIn('"undock"', body)

    def test_no_destination_present_reads_as_permitted_not_refused(self):
        """The direction that matters: `Nothing -> True`, not the reverse. A
        mutation flipping this boolean is exactly run 6's bug reintroduced,
        and `LocalEscalationStepIsPermittedTest` above is what would catch it
        running -- this pins the source shape it depends on."""
        body = body_of(self.source, "escalationDestinationIsPermitted")
        # `case entry.destination of` then `Nothing -> True` before the
        # `Just destination ->` arm that goes on to branch on `systemName`.
        self.assertRegex(
            re.sub(r"\s+", " ", body),
            r"case entry\.destination of\s*Nothing\s*->\s*True".replace(" ", r"\s*"))


if __name__ == "__main__":
    unittest.main()
