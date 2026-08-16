"""saxrat's lock batch takes the in-range prefix rather than filtering.

`overviewEntriesToLockInOneStep` was built by `List.filter`ing the candidate
list down to the rows in lock range. That is safe only while the candidate list
is in distance order, so that the rows in range are a prefix of it and filtering
can reorder nothing.

**It stopped being in distance order when PR #253 landed.**
`decideActionInAnomaly` puts `|> List.sortBy combatPriorityTier` ahead of the
distance order the helper returns rows in, and `overviewEntriesToLock` derives
from that sorted list -- so a warp-disrupting row the ship cannot reach can sit
at the head, and filtering drops it and promotes the rats behind it. The bot then
batches those rats and never approaches the scrambler, which is the one row the
tier exists to put first.

**Nothing failed when the premise expired.** The comment at the batch site went
on saying "both lists are sorted by distance" -- true when it was written, false
the moment the sort landed above it -- and the mission runner's own
`lockBatchRowsInReach` went on asserting that saxrat could not suffer this
("There the candidate list is sorted by distance alone"). Both are corrected, in
both files, and `TheExpiredJustificationIsCorrectedInBothFiles` is what goes red
if either sentence comes back.

`test_a_scrambler_out_of_reach_is_no_longer_skipped` is the case that would have
caught this when #253 landed: a priority-sorted list with an out-of-reach head,
with the old construction and the new one run side by side over the *same* rows,
so what separates them is the change and not the fixture.

**What the bot does in the new edge case, asserted rather than described.** A
head the ship cannot reach makes `lockBatchRowsInReach` answer 0, `lockBatchSize`
answer `max 1 0` = 1, and the batch one row -- never zero. The call site's
`1 < List.length` guard therefore declines to batch and hands the reading to
`lockTargetFromOverviewEntry`, whose out-of-range branch double-clicks the row
(or warps to it past `approachRangeLimitMeters`). So the reading is spent closing
distance rather than declined, which is the hazard PR #257 shipped: a step on a
hot path that can decline forever. `TheShortBatchIsStillAnAnswer` asserts both
halves -- the batch is never empty, and the branch it falls through to acts.

The rules are executed through the real `Bot.elm` in `elm repl` and the overview
rows they are asked about come from the real `EveOnline.ParseUserInterface`, so a
hand-written record cannot drift from what the parser would have produced. The
wiring and the two corrected comments are read out of the source, the wiring
through a reader sliced by **indentation** since the binding under test builds a
record literal.

**Two cases are weaker than the rest and say so.** `oldBatch` and `newBatch` are
written in `BatchRepl` rather than reached through `decideActionInAnomaly`, which
takes a whole `BotDecisionContext` -- so the executable comparison shows what the
two constructions *do* and cannot notice the site being reverted to the filter.
What pins the site is `TheDecisionSiteIsWiredToTheRule`, and
`test_saxrat_batched_lock_clicks`' own wiring case reads it too. Mutating the
site fails those two and none of the executable ones, which is how that division
of labour was established rather than assumed.

Nothing here reads a live game client, a running bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_BOT_ELM, SaxratRepl, collapsed, source_of)
from test_ewar_priority_targets import WARP_DISRUPTION, overview, rat

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
APPS = (("saxrat", SAXRAT_BOT_ELM), ("mission runner", MISSION_RUNNER_BOT_ELM))

# The lock range the shipped `targeting-range` gives with nothing learned, and
# the two distances either side of it the fixtures use. 90 km is out of reach
# and still on grid, so the row is a candidate the batch has to reckon with
# rather than one `overviewEntryDistanceIsOnGrid` already dropped.
LOCK_RANGE = 66000
OUT_OF_REACH = "90,000 m"
IN_REACH = ("10,000 m", "20,000 m", "30,000 m")


def indented_block(source, name, indent):
    """A binding's right-hand side, sliced by indentation.

    `let_binding`'s shape -- read to the next ` <name> = ` -- stops at a record
    literal, and the binding this file asks about builds one. PRs #147, #156,
    #159 and #162 each paid for that once with an assertion that passed having
    read nothing.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    for match in re.finditer(r"\n([ ]*)(\S)", rest):
        if len(match.group(1)) <= len(indent):
            return rest[:match.start()]
    return rest


def top_level_block(source, name):
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def declaration(source, name):
    """The same, with its doc comment -- a comment that drifts is the bug."""
    body = top_level_block(source, name)
    start = source.index(body)
    prefix = source[:start]
    if prefix.rstrip().endswith("-}"):
        return source[prefix.rindex("{-|"):start + len(body)]
    return body


def anomaly_decision_source():
    return top_level_block(source_of(SAXRAT_BOT_ELM), "decideActionInAnomaly")


class BatchRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus the two batch constructions expressed.

    `inReach` is the one thing restated here rather than reached for, because
    `overviewEntryIsWithinLockRange` takes a whole `BotDecisionContext` while the
    threshold rule under it takes a record. It is defined **once** and handed to
    both constructions, so the comparison below is about the prefix against the
    filter and not about two different notions of reach.
    """

    HELPERS = [
        "lockState = { fromSetting = %d, statedMeters = Nothing"
        " , provenAtMeters = Nothing, refusedAtMeters = Nothing"
        " , attempt = Nothing }" % LOCK_RANGE,
        "inReach = \\e -> e.objectDistanceInMeters"
        " |> Result.map (\\m -> m <= lockRangeThresholdInMeters lockState)"
        " |> Result.withDefault False",
        # The candidate list exactly as `decideActionInAnomaly` builds it: the
        # real helper, the real tier sort, the real rendered-row filter.
        "candidates = \\parsed -> parsed"
        " |> Maybe.map (overviewEntriesToAttackFromReadingFromGameClient [])"
        " |> Maybe.withDefault []"
        " |> List.sortBy combatPriorityTier"
        " |> List.filter overviewEntryIsDisplayed"
        " |> List.take 6"
        " |> List.filter (overviewEntryIsTargetedOrTargeting >> not)",
        "situation = \\held take reachable probe ->"
        " { targetsHeld = held, rowsToTake = take"
        " , rowsLockableNow = reachable, probeIsDue = probe }",
        # What the site used to do: filter, then take.
        "oldBatch = \\rows -> (rows |> List.filter inReach) |> List.take"
        " (lockBatchSize (situation 1 6"
        " (rows |> List.filter inReach |> List.length) False))",
        # What it does now: take the in-range prefix of the candidate list.
        "newBatch = \\rows -> rows |> List.take"
        " (lockBatchSize (situation 1 6"
        " (rows |> List.map inReach |> lockBatchRowsInReach) False))",
        "namesOf = \\rows -> rows"
        " |> List.map (.objectName >> Maybe.withDefault \"?\")"
        " |> String.join \",\"",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class SharedRepl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def ask(self, expressions, definitions=()):
        return self.repl.evaluate(
            expressions, definitions=self.repl.with_helpers(definitions))

    def say(self, expressions, definitions=()):
        return self.repl.strings(
            expressions, definitions=self.repl.with_helpers(definitions))

    def reading(self, name, rows):
        return self.repl.reading_binding(name, [overview(rows)])


class TheBatchNeverReachesPastARowItCannotLock(SharedRepl):
    """The prefix rule itself, on plain booleans.

    Ported from the mission runner, where it has been since #178 and where its
    doc comment argued -- wrongly, after #253 -- that saxrat did not need it.
    """

    def test_a_head_the_ship_cannot_reach_answers_zero(self):
        """Which drops the batch to one row and hands the reading to the single
        path, whose out-of-range branch approaches it."""
        self.assertEqual(
            self.ask([
                "lockBatchRowsInReach [ False, True, True, True ] == 0",
                "lockBatchRowsInReach [ False ] == 0",
                "lockBatchRowsInReach [] == 0",
                # And a batch of zero is never an answer.
                "lockBatchSize (situation 1 6 0 False) == 1",
            ]), [True] * 4,
            "a row the ship cannot reach no longer stops the batch, so a "
            "scrambler out of range is skipped and the rats behind it locked "
            "instead")

    def test_it_stops_at_the_first_row_out_of_reach(self):
        """A prefix, not a count: the rows behind a gap are not candidates for
        *this* step however close they are."""
        self.assertEqual(
            self.ask([
                "lockBatchRowsInReach [ True, True, False, True, True ] == 2",
                "lockBatchRowsInReach [ True, False, True ] == 1",
                "lockBatchRowsInReach [ True, True, True ] == 3",
            ]), [True] * 3,
            "the reachability rule counts past a row the ship cannot lock, so "
            "a batch would reorder the candidate list")


class ThePrioritySortedListIsWhyThisIsNeeded(SharedRepl):
    """The case that would have caught this when #253 landed.

    Real rows, the real attack helper, the real tier sort, and the two batch
    constructions run side by side over the same list.
    """

    SCRAMBLER = "far scrambler"
    NEAR = ["near rat a", "near rat b", "near rat c"]

    def grid(self, scrambler_distance):
        return [rat(scrambler_distance, name=self.SCRAMBLER,
                    hints=[WARP_DISRUPTION])] + [
            rat(distance, name=name)
            for distance, name in zip(IN_REACH, self.NEAR)]

    def test_the_tier_sort_really_puts_the_out_of_reach_row_first(self):
        """The premise. Without it the rest of this class proves nothing: the
        row sits at the head *because* of the tier, not because of its
        distance -- it is the furthest row on the grid."""
        self.assertEqual(
            self.say(["namesOf (candidates grid)"],
                     [self.reading("grid", self.grid(OUT_OF_REACH))]),
            [",".join([self.SCRAMBLER] + self.NEAR)],
            "the candidate list is not tier-sorted, so this file is testing "
            "something other than the situation #253 created")

    def test_a_scrambler_out_of_reach_is_no_longer_skipped(self):
        """The whole change, as a difference between two constructions.

        The old one answers the three rats behind the scrambler -- a batch that
        locks them and leaves the row that can stop the ship leaving unlocked
        and unapproached. The new one answers the scrambler alone, which is one
        row, which is what sends the reading to the approach.
        """
        old, new = self.say(
            ["namesOf (oldBatch (candidates grid))",
             "namesOf (newBatch (candidates grid))"],
            [self.reading("grid", self.grid(OUT_OF_REACH))])
        self.assertEqual(
            old, ",".join(self.NEAR),
            "the filtering construction is not doing what this change is "
            "about, so the comparison below says nothing")
        self.assertEqual(
            new, self.SCRAMBLER,
            "the batch still reaches past a row the ship cannot lock: the "
            "warp-disrupting row at the head is dropped and the rats behind it "
            "are locked instead, which is exactly the failure the mission "
            "runner's `lockBatchRowsInReach` exists to refuse")

    def test_a_scrambler_in_reach_is_batched_exactly_as_before(self):
        """The control, and the scope of the change: where the head is
        reachable the two constructions agree, so nothing about an ordinary
        engagement moves."""
        old, new = self.say(
            ["namesOf (oldBatch (candidates grid))",
             "namesOf (newBatch (candidates grid))"],
            [self.reading("grid", self.grid("40,000 m"))])
        self.assertEqual(old, new)
        self.assertEqual(
            new, ",".join([self.SCRAMBLER] + self.NEAR[:2]),
            "a reachable head no longer leads the batch, so the change is not "
            "confined to the case it was made for")

    def test_a_grid_with_no_priority_row_is_untouched(self):
        """Every row in reach and in distance order -- the common case, where
        the prefix and the filter are the same list by construction."""
        rows = [rat(distance, name=name)
                for distance, name in zip(IN_REACH, self.NEAR)]
        old, new = self.say(
            ["namesOf (oldBatch (candidates grid))",
             "namesOf (newBatch (candidates grid))"],
            [self.reading("grid", rows)])
        self.assertEqual(old, new)
        self.assertEqual(new, ",".join(self.NEAR[:3]))


class TheShortBatchIsStillAnAnswer(SharedRepl):
    """PR #257's hazard: a step on a hot path that can decline forever.

    A batch that comes back empty where it used to come back non-empty is the
    same shape, so both halves are asserted -- the batch is never empty, and the
    branch the short batch falls through to acts on the reading rather than
    waiting on it.
    """

    def test_a_head_out_of_reach_gives_exactly_one_row_never_none(self):
        rows = [rat(OUT_OF_REACH, name="far scrambler",
                    hints=[WARP_DISRUPTION])] + [
            rat(distance, name="near rat %d" % index)
            for index, distance in enumerate(IN_REACH)]
        self.assertEqual(
            self.ask(["(newBatch (candidates grid) |> List.length) == 1",
                      "(newBatch (candidates grid) |> List.isEmpty) == False"],
                     [self.reading("grid", rows)]),
            [True, True],
            "the batch came back empty or long where the head is out of reach; "
            "empty would make the call site's `1 < List.length` guard decline "
            "both the batch and the single lock")

    def test_the_batch_size_is_never_zero_whatever_it_is_told(self):
        """`max 1` is what makes that true, and it is asserted over the whole
        grid of inputs rather than at one point."""
        self.assertEqual(
            self.ask([
                "List.range 0 6 |> List.concatMap (\\held ->"
                " List.range 0 6 |> List.concatMap (\\take ->"
                " List.range 0 6 |> List.map (\\reach ->"
                " lockBatchSize (situation held take reach False))))"
                " |> List.all (\\n -> 1 <= n)",
            ]), [True],
            "some situation makes the batch zero rows, and a batch of zero is "
            "not an answer -- it is a branch that clicks nothing")

    def test_the_single_path_acts_on_the_row_rather_than_waiting_on_it(self):
        """So the reading a short batch produces is spent closing distance.

        Read out of the source: the out-of-range branch double-clicks the row
        inside `approachRangeLimitMeters` and warps to it beyond, and neither
        answer is `waitForProgressInGame`.
        """
        branch = collapsed(top_level_block(
            source_of(SAXRAT_BOT_ELM), "lockTargetFromOverviewEntry"))
        out_of_range = branch[branch.index("Object is not in range"):]
        self.assertIn("doubleClickUiElement overviewEntry.uiNode", out_of_range,
                      "the out-of-range branch no longer approaches the row, "
                      "so a head the ship cannot reach is a reading spent on "
                      "nothing and the distance never closes")
        self.assertIn("warpToDistantOverviewEntry", out_of_range)
        self.assertNotIn("waitForProgressInGame", out_of_range,
                         "the out-of-range branch waits instead of acting, "
                         "which is a step that can decline forever")


class TheDecisionSiteIsWiredToTheRule(unittest.TestCase):
    """The lines that could revert this while everything still compiled."""

    def setUp(self):
        self.binding = collapsed(indented_block(
            anomaly_decision_source(), "overviewEntriesToLockInOneStep",
            indent="        "))

    def test_the_batch_takes_the_prefix_rather_than_filtering(self):
        self.assertIn("lockBatchRowsInReach", self.binding,
                      "the batch no longer counts the in-range prefix, so the "
                      "priority ordering can be skipped past")
        self.assertIn("overviewEntriesToLock |> List.take", self.binding,
                      "the batch is taken from something other than the front "
                      "of the candidate list")
        self.assertNotIn("overviewEntriesToLockInRange", self.binding,
                         "the batch is built by filtering the candidate list, "
                         "which drops a row the ship cannot reach and promotes "
                         "the ones behind it")

    def test_the_probe_still_reads_the_in_range_filter(self):
        """`overviewEntriesToLockInRange` is not deleted, and must not be.

        #150's probe is a measurement and may only be made with a row the ship
        can already lock, so `rowsToSpare` is a count of everything in range and
        stays one -- the prefix is about the *batch*, which is a different
        question about the same list.
        """
        decision = collapsed(anomaly_decision_source())
        self.assertIn(
            "rowsToSpare = overviewEntriesToLockInRange |> List.length",
            decision,
            "the probe no longer counts the rows in range, so a probe can be "
            "made with a row the ship would have to fly at first")
        self.assertIn("overviewEntriesToLockInRange |> List.head", decision,
                      "the probe's own row no longer comes from the rows in "
                      "range")

    def test_the_tier_sort_is_still_what_makes_the_prefix_necessary(self):
        """One sort, ahead of the distance order, in both apps -- the premise
        the whole change rests on."""
        for name, path in APPS:
            with self.subTest(app=name):
                source = collapsed(source_of(path))
                self.assertEqual(
                    source.count("|> List.sortBy combatPriorityTier"), 1,
                    "one sort, so two places cannot come to disagree about "
                    "the order the fight sees")


class TheExpiredJustificationIsCorrectedInBothFiles(unittest.TestCase):
    """Both comments were wrong and correcting them is part of the change.

    The mission runner's asserted saxrat could not suffer this; saxrat's
    defended the filter with the same claim. A merged PR body is not a record --
    the next reader of either file reads the file.
    """

    EXPIRED = (
        "sorted by distance alone",
        "both lists are sorted by distance",
        "filtering could not reorder anything",
    )

    def test_neither_file_still_claims_the_list_is_in_distance_order(self):
        for name, path in APPS:
            source = source_of(path)
            for phrase in self.EXPIRED:
                with self.subTest(app=name, phrase=phrase):
                    self.assertNotIn(
                        phrase, source,
                        "the expired justification is back: the candidate list "
                        "is sorted by `combatPriorityTier` ahead of distance in "
                        "both apps, so nothing may say it is in distance order")

    def test_both_files_name_the_change_that_expired_it(self):
        """#253 is what a reader has to be able to find, in the file rather
        than in a PR body."""
        for name, path in APPS:
            with self.subTest(app=name):
                self.assertIn(
                    "#253", declaration(source_of(path),
                                        "lockBatchRowsInReach"),
                    "the rule's doc comment does not name the reordering that "
                    "made it necessary here")

    def test_both_apps_compute_the_prefix_the_same_way(self):
        """A port that keeps one copy and lets the other drift is what this
        refuses; the failure would be quiet, since a bot that batches past an
        unreachable head reads exactly like one that never meets a scrambler."""
        bodies = {name: top_level_block(source_of(path), "lockBatchRowsInReach")
                  for name, path in APPS}
        self.assertEqual(bodies["saxrat"], bodies["mission runner"])

    def test_the_two_doc_comments_are_allowed_to_differ_and_do(self):
        """Each argues from its own app's history -- the mission runner's from
        #178 and the correction, saxrat's from having filtered until now -- so
        they are deliberately not compared byte for byte. Both must carry the
        property the rule is for."""
        docs = {name: declaration(source_of(path), "lockBatchRowsInReach")
                for name, path in APPS}
        self.assertNotEqual(docs["saxrat"], docs["mission runner"])
        for name, doc in docs.items():
            with self.subTest(app=name):
                self.assertIn("prefix", collapsed(doc))
                self.assertIn("combatPriorityTier", collapsed(doc))
