"""Tests for wingus's half of #205 -- the same dead warp-end trigger as #194.

`eve-online-wingus` carries #194 verbatim:

```elm
weJustFinishedWarping =
    (botMemoryBefore.shipWarpingInLastReading == Just True) && (shipIsWarping == Just False)
```

`shipIsWarping` is a `Maybe` over the maneuver the client **names** -- `Just
True` for `Warp`, `Just False` for some *other* named maneuver, `Nothing` for
none at all -- and the indication container is still present but names nothing
at the end of a warp, so the real transition is `Just True -> Nothing`. The
condition above could therefore never fire at the end of a warp, which made
the arrival snapshot -- `anomalyMemoryWithOtherPilotsOnArrival`, gated on
`weJustFinishedWarping` -- dead by construction: `otherPilotsFoundOnArrival`
could only ever be written as `[]`.

**A further finding, stated rather than fixed: wingus never reads the field
back at all.** Unlike saxrat and the combat anomaly bot, which both carry
`findReasonToAvoidAnomalyFromMemory` reading `otherPilotsFoundOnArrival` to
decide whether to leave, wingus's own anomaly branch
(`decideNextActionWhenInSpace`) looks up the same `MemoryOfAnomaly` only for
`arrivalTime`, to print how long the ship has been there -- searched for and
not found anywhere else in the file. So this change makes the *write* correct
rather than permanently `[]`, but there is still nothing here that would act on
it; wingus is a fleet-follow bot with no leave-an-anomaly decision of its own.
Wiring one up is a behaviour change with its own argument to make, which is not
what #205 asks for and is not this change. `TheOldConditionIsGone` pins what
does exist: the field is written on the right reading now, and nothing more is
claimed.

**The fix is #201's, taken whole rather than re-derived.** `shipWarpingFromReading`
and `warpJustEnded` are ported byte-identical from `eve-online-saxrat` (and,
transitively, `eve-online-combat-anomaly-bot`, which #201 already keeps in
step with saxrat) -- see this file's own `TheTwoDeclarationsMatchSaxratsByteForByte`.
`warpJustEnded` reads three things rather than two: the previous reading was
`Just True`, **the ship UI is present now**, and the current reading is not
`Just True`. The middle clause is load-bearing: `Nothing` is equally what a
reading with no ship UI at all gives -- docked, a client that did not render, a
reading across a session change -- and a fix written as `/= Just True` and
nothing else would call every one of those an arrival.

**Wingus keeps its own single-reading snapshot design**, unlike #201's fix in
saxrat and the combat anomaly bot, which widened "arrival" into a bounded
window (at a bound of zero, which the corpus in #201 shows is equivalent to a
single reading anyway). Wingus's snapshot already runs on exactly the reading
`weJustFinishedWarping` answers `True` for, which is what a window of zero
readings would do too -- so only the trigger moves, not the shape around it.

**Scope when this file was written: wingus only.** `eve-online-mission-runner`
carried the identical `(shipIsWarping == Just False)` shape for two *different*
readers -- `droneAbandonmentAfterReading`'s `shipLeftThisReading`, and #154's
per-warp ammo-swap give-up retry -- and PR #233 kept those separate
deliberately: they are behaviour changes with their own blast radius, and each
needed its own argument and its own cases. **That work has since been done**,
which retired `TheMissionRunnerIsUntouched` -- see
`TheFourAppsCarryTheSameWorkingTrigger`, which replaces it, and
`test_mission_runner_warp_end_trigger.py` for the argument and the cases.

**Verified without a live client.** The transition is executed through the
real `Bot.elm` in `elm repl`, with readings built from the shape captured off
the live client during saxrat run 29 (and run through the real
`EveOnline.ParseUserInterface`, since it is not app-specific and is vendored
identically here) -- `TheTransitionIsSeenOnTheClientsOwnShape` reuses the
fixtures `test_arrival_pilot_window.py` built for exactly this shape. The old
condition is executed on the same pair and asserted to answer `False`, so a
revert fails with the reason rather than an unrelated mismatch six rules away.

Mutated by hand while this change was written, watching a named case fail each
time: restoring the old `Just False` condition inside wingus's own copy of
`warpJustEnded` breaks `test_a_warp_ending_into_stillness_is_seen`; dropping
the `readingNow.shipUI /= Nothing` clause from it breaks
`test_a_reading_with_no_ship_ui_is_not_an_arrival`; and reverting
`weJustFinishedWarping` to the old two-line shape breaks
`TheOldConditionIsGone.test_weJustFinishedWarping_uses_the_shared_rule`.

**Unverified: any of it running.** `FoundOtherPilotOnArrival` has never been
constructed by wingus in a recorded run, and wingus may not be flown at all --
nothing here has been watched against a live client. What to watch on the
first run that warps is whatever wingus's own status line prints about the
anomaly memory (wingus has no `describeArrivalWindow`-style clause, since it
never took #201's window widening -- the snapshot is silent the way it always
was, and only the leave branch firing, or a run's own log showing
`otherPilotsFoundOnArrival` non-empty, would say the trigger is live).

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import REPO_DIR, open_repl
from test_saxrat_ported_guards import SAXRAT_BOT_ELM, SaxratRepl, source_of
from test_arrival_pilot_window import (
    COMBAT_ANOMALY_BOT_ELM,
    WARP_READINGS,
    body_of_declaration,
    indented_binding,
    without_block_comments,
)

WINGUS_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingus")
WINGUS_BOT_ELM = os.path.join(WINGUS_DIR, "Bot.elm")

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The two declarations #201 built and #205 asks wingus to take whole.
SHARED_DECLARATIONS = ("shipWarpingFromReading", "warpJustEnded")

# The dead condition, quoted from the issue and from the source every app
# carried it in. Matched without its parentheses, because two apps quote the
# shape in a doc comment and the code is what this is about -- the callers
# below strip block comments first.
OLD_CONDITION = "shipIsWarping == Just False"

# Every app that carries the working trigger, once #205 finished the sweep
# #194 started. The order is the order they took it.
APPS_WITH_THE_RULE = (
    ("saxrat", SAXRAT_BOT_ELM),
    ("combat anomaly bot", COMBAT_ANOMALY_BOT_ELM),
    ("wingus", WINGUS_BOT_ELM),
    ("mission runner", MISSION_RUNNER_BOT_ELM),
)


class WingusRepl(SaxratRepl):
    """The same harness and preamble as saxrat's, pointed at wingus.

    `reading_binding` is inherited unchanged: it is a pure builder over a JSON
    tree and the standard parser, naming nothing saxrat-specific, so the same
    `WARP_READINGS` fixtures `test_arrival_pilot_window.py` built can be handed
    to this repl as they stand.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingus-repl-")
        kwargs.setdefault("app_dir", WINGUS_DIR)
        super().__init__(**kwargs)


def declaration(path, name):
    """One top-level declaration, doc comment and all, by exact text match.

    Mirrors `TheTwoAppsCarryTheSameRules.declaration` in
    `test_arrival_pilot_window.py` -- kept local rather than imported because
    that one is a bound method on a `unittest.TestCase` there.
    """
    match = re.search(
        r"(\{-\|(?:(?!-\})[\s\S])*?-\}\n)?%s :[\s\S]*?(?=\n\n\n)"
        % re.escape(name), source_of(path))
    assert match, "no declaration named %r in %s" % (name, path)
    return match.group(0)


class TheTwoDeclarationsMatchSaxratsByteForByte(unittest.TestCase):
    """#201 built these once; #205 asks wingus to take them whole.

    Nothing in either declaration is app-specific -- they are a `Maybe` read
    off a ship UI and a three-clause boolean over it -- so a copy that drifts
    from saxrat's is a bug in whichever one drifted, and the drift is silent:
    both still compile, both still answer.
    """

    def test_shipWarpingFromReading_and_warpJustEnded_are_byte_identical(self):
        for name in SHARED_DECLARATIONS:
            wingus_text = declaration(WINGUS_BOT_ELM, name)
            saxrat_text = declaration(SAXRAT_BOT_ELM, name)
            self.assertEqual(
                wingus_text, saxrat_text,
                "wingus's %s has drifted from saxrat's -- both compile and "
                "both answer, so the drift would be silent" % name)


class TheOldConditionIsGone(unittest.TestCase):
    """`weJustFinishedWarping`'s own binding, read out of the source.

    Not an expression `elm repl` can be asked to evaluate on its own -- it is a
    `let` binding inside `updateMemoryForNewReadingFromGame` -- so it is read
    with the same indentation-sliced reader `test_arrival_pilot_window.py`
    uses for the equivalent binding in saxrat and the combat anomaly bot.
    """

    def test_weJustFinishedWarping_uses_the_shared_rule(self):
        update = body_of_declaration(
            without_block_comments(source_of(WINGUS_BOT_ELM)),
            "updateMemoryForNewReadingFromGame")
        binding = indented_binding(update, "weJustFinishedWarping")
        self.assertIn(
            "warpJustEnded", binding,
            "wingus's weJustFinishedWarping no longer calls the shared "
            "warpJustEnded rule, which is #201's fix and the whole of "
            "wingus's half of #205")
        self.assertNotIn(
            "Just False", binding,
            "wingus's weJustFinishedWarping still spells out the "
            "unreachable Just False condition #194 and #205 are about -- "
            "restoring it is exactly the mutation this case exists to catch")

    def test_the_snapshot_is_still_gated_on_the_fixed_trigger(self):
        """The write this change makes reachable, and only that write."""
        update = body_of_declaration(
            without_block_comments(source_of(WINGUS_BOT_ELM)),
            "updateMemoryForNewReadingFromGame")
        snapshot = indented_binding(
            update, "anomalyMemoryWithOtherPilotsOnArrival")
        self.assertIn(
            "weJustFinishedWarping", snapshot,
            "wingus no longer gates the arrival snapshot on "
            "weJustFinishedWarping, so the fixed trigger is not what decides "
            "when otherPilotsFoundOnArrival is written")
        self.assertIn(
            "getNamesOfOtherPilotsInOverview", snapshot,
            "wingus's arrival snapshot no longer reads the live overview, so "
            "there is nothing left for the fixed trigger to arm")

    def test_wingus_still_has_no_reader_of_the_field_it_writes(self):
        """A finding stated plainly, not a claim this change fixes.

        Neither saxrat's nor the combat anomaly bot's
        `findReasonToAvoidAnomalyFromMemory` exists here, and no other
        declaration reads `otherPilotsFoundOnArrival` back -- confirmed by
        searching the whole file rather than one function, since the reader
        could be named anything. Wingus follows fleet warps rather than
        choosing or leaving anomalies on its own, so there may be nothing here
        that *should* read it. This change makes the write correct; it does
        not add a consumer, and this case is what would notice if one showed
        up naming the field without also being counted here.
        """
        source = without_block_comments(source_of(WINGUS_BOT_ELM))
        readers = [
            line for line in source.splitlines()
            if "otherPilotsFoundOnArrival" in line
            and "otherPilotsFoundOnArrival =" not in line
            and ", otherPilotsFoundOnArrival " not in line
        ]
        self.assertEqual(
            readers, [],
            "wingus now reads otherPilotsFoundOnArrival somewhere this file "
            "did not expect (%r) -- a leave-on-arrival branch may have been "
            "added, which is a behaviour change with its own evidence to "
            "give, not something this change's cases cover" % readers)


class TheTransitionIsSeenOnTheClientsOwnShape(unittest.TestCase):
    """The transition itself, executed through wingus's own compiled code.

    The readings are the ones captured off the live client during saxrat run
    29 and built by `test_arrival_pilot_window.py`: the ship UI's indication
    container is still present when a warp ends and holds only the location
    labels, no maneuver word. Nothing in wingus's source had ever been asked
    whether it notices that -- every case that shipped with the dead condition
    asked about what happens *after* an arrival, never about whether one is
    seen at all -- which is how a total defect survives in reachable code.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingusRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_parse_the_way_this_file_assumes(self):
        answers = self.repl.evaluate(
            ["warpingIn warping == Just (Just True)",
             "shipUIPresentIn landed == Just True",
             "indicationPresentIn landed == Just True",
             "warpingIn landed == Just Nothing",
             "warpingIn orbiting == Just (Just False)",
             "shipUIPresentIn noShipUI == Just False"],
            WARP_READINGS)
        self.assertEqual(
            answers, [True] * 6,
            "wingus's parser does not make of these fixtures what this file "
            "assumes it does -- wingus vendors EveOnline.ParseUserInterface "
            "the same way every other app here does, and if that has "
            "drifted nothing below means anything")

    def test_a_warp_ending_into_stillness_is_seen(self):
        """The case #194 and #205 are, and the one nothing had ever run."""
        answers = self.repl.evaluate(
            ["warpEndSeen warping landed == Just True"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "wingus does not notice a warp ending when the client stops "
            "naming a manoeuvre, which is what the client actually does -- "
            "so the arrival snapshot never fires and nothing downstream of "
            "it can either")

    def test_the_condition_this_replaces_would_have_missed_it(self):
        """The defect, executed on the reading it had to answer `True` on.

        Kept as its own case so a revert fails with the reason rather than an
        arithmetic mismatch six rules away, the same convention #201's own
        suite uses.
        """
        answers = self.repl.evaluate(
            ["oldWarpEndSeen warping landed == Just False"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "wingus's old Just False condition now answers True at the end "
            "of a warp, which the captured client reading says it cannot -- "
            "so this case is measuring something other than #194/#205")

    def test_a_warp_ending_into_another_maneuver_is_still_seen(self):
        """The one shape the old condition did handle, not lost in the fix."""
        answers = self.repl.evaluate(
            ["warpEndSeen warping orbiting == Just True"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "wingus no longer notices a warp that ends straight into "
            "another maneuver, which is the only end of warp the old "
            "condition could see")

    def test_a_reading_with_no_ship_ui_is_not_an_arrival(self):
        """The half of `Nothing` that must not count.

        `shipWarpingFromReading` answers `Nothing` both for a ship that
        stopped maneuvering and for a reading that could not see the ship at
        all -- docked, a client that did not render, a reading across a
        session change. A fix written as `/= Just True` and nothing else
        would call every one of those an arrival, and wingus would take an
        arrival snapshot of a grid it never landed on.
        """
        answers = self.repl.evaluate(
            ["warpEndSeen warping noShipUI == Just False"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "wingus treats a reading with no ship UI as a warp ending, so a "
            "client that failed to render one arms the arrival snapshot")

    def test_a_reading_still_in_warp_is_not_an_arrival(self):
        answers = self.repl.evaluate(
            ["warpEndSeen warping warping == Just False"], WARP_READINGS)
        self.assertEqual(
            answers, [True], "wingus calls every reading of a warp its end")

    def test_a_session_that_was_not_warping_before_is_not_an_arrival(self):
        """`Nothing -> Nothing` is not a warp ending either."""
        answers = self.repl.evaluate(
            ["warpEndSeen noShipUI landed == Just False",
             "warpEndSeen noShipUI noShipUI == Just False",
             "warpEndSeen landed landed == Just False"],
            WARP_READINGS)
        self.assertEqual(
            answers, [True] * 3,
            "wingus restarts the arrival trigger on a session that has not "
            "warped, which makes every reading an arrival")


class TheFourAppsCarryTheSameWorkingTrigger(unittest.TestCase):
    """What `TheMissionRunnerIsUntouched` became once #205 was finished.

    That case asserted the mission runner **still had** the dead condition. It
    was PR #233's own scope line pinned rather than assumed: wingus was fixed,
    the mission runner deliberately was not, and the case is what would have
    noticed if that stopped being true silently. It has now stopped being true
    on purpose -- issue #205 is exactly that work, and
    `test_mission_runner_warp_end_trigger.py` carries its argument and its
    cases -- so a case recording the defect would be colliding with the change
    that fixes it, which this repo has now been bitten by twice.

    **Deleting it would drop something worth keeping, so it is replaced rather
    than removed.** What was worth noticing was never "the mission runner is
    behind"; it is that four apps carry one rule that is app-specific in no
    part of it, and that a copy which drifts still compiles and still answers.
    So all four are compared byte for byte here, and none of them may carry the
    shape #194 found dead. A fifth app growing its own copy, or one of the four
    drifting from the rest, goes red -- which makes a future divergence a
    decision somebody argues for rather than one the suite lets happen.
    """

    def test_all_four_apps_carry_the_same_two_declarations(self):
        for name in SHARED_DECLARATIONS:
            texts = {app: declaration(path, name)
                     for app, path in APPS_WITH_THE_RULE}
            self.assertEqual(
                len(set(texts.values())), 1,
                "%s is not the same declaration in all four apps -- every one "
                "of them compiles and answers either way, so the drift is "
                "silent. Lengths by app: %r"
                % (name, {app: len(text) for app, text in texts.items()}))

    def test_no_app_still_carries_the_dead_condition(self):
        """Block comments stripped, because two of the four quote the shape.

        saxrat and the combat anomaly bot explain #194 in a doc comment by
        writing the condition out, so a search over the raw source finds the
        prose rather than the code -- and would go on passing with the code
        reverted in an app that carries no such comment.
        """
        for app, path in APPS_WITH_THE_RULE:
            # `assertNotIn` would print the whole `Bot.elm` as the container,
            # which is tens of thousands of lines of failure output for a
            # one-line finding.
            self.assertFalse(
                OLD_CONDITION in without_block_comments(source_of(path)),
                "%s carries #194's unreachable condition in code again -- it "
                "cannot answer True at the end of a warp, and every case "
                "downstream of it passes while it is there" % app)


if __name__ == "__main__":
    unittest.main()
