"""Tests for the mission runner's half of #205 -- #194's dead warp-end trigger.

`eve-online-mission-runner` carried the condition #194 turned out to be:

```elm
weJustFinishedWarping =
    (botMemoryBefore.shipWarpingInLastReading == Just True) && (shipIsWarping == Just False)
```

`shipIsWarping` is a `Maybe` over the maneuver the client **names** -- `Just
True` for `Warp`, `Just False` for some *other* named maneuver, `Nothing` for
none at all -- and the indication container is still present but names nothing
at the end of a warp. So the real transition is `Just True -> Nothing`, and the
condition above could never answer `True` at the end of a warp.
`TheTransitionIsSeenOnTheClientsOwnShape` executes that pair rather than
restating it, because a condition that is always `False` makes every case
downstream of it pass, which is how a total defect survived in reachable code.

**The fix is #201's, taken whole rather than re-derived.** `shipWarpingFromReading`
and `warpJustEnded` are ported byte-identical from `eve-online-saxrat`, which
already keeps them in step with `eve-online-combat-anomaly-bot` (#201) --
every app that carries the rule is compared here, in
`TheThreeAppsCarryTheSameWorkingTrigger`. `warpJustEnded` reads three
things rather than two: the previous reading was `Just True`, **the ship UI is
present now**, and the current reading is not `Just True`. The middle clause is
load-bearing, and it is load-bearing *here* in a way it is not in the anomaly
bots: this bot docks, which is where the ship UI legitimately goes away, and a
fix written as `/= Just True` and nothing else would make every docking reading
a warp ending -- which for the drone rule is `shipLeftThisReading` firing twice
for one departure.

**This is a behaviour change to two live consumers, which is why #233 deferred
it rather than overlooking it.** Both are executed below through the real
trigger over the real captured readings, so what the cases assert is what the
consumers now do rather than what this file thinks they do:

  - `droneAbandonmentAfterReading`'s `shipLeftThisReading` is
    `weJustFinishedWarping || (dockedNow && not dockedInLastReading)`, and only
    the docking half has ever fired. So drones left in space have been noticed
    when the ship docks and never when it warps out of a pocket -- which is the
    case the rule's own doc comment says it is for ("a ship lining up to warp
    still has time to get its drones back, and run 11 spent 21 readings of
    `I am in warp` doing exactly that"). It now fires on the arrival, records
    the count and the *sighting's* place, and drops the sighting so the warp
    home and the dock that follows it still report one event rather than two.
    `TheDroneAbandonmentNowFiresOnTheWarpHalf` runs all of that.
    **Nothing acts on the verdict**, which is #59's own posture and is pinned
    here rather than assumed -- the newly-live half writes a decision line and a
    status clause and drives no branch.
  - #154's per-warp ammo-swap give-up retry, through
    `ammoSwapGiveUpAfterReading`. A `GunsDidNotComeBack` verdict is supposed to
    be cleared on the next warp and was never cleared at all, so a swap that
    failed once stayed given up for the session -- **while the status line said
    `off until the next warp` on every reading of it**, which is a promise the
    bot could not keep. `TheAmmoSwapGiveUpIsNowRetriedOnAWarp` runs the retry
    and both of the verdicts that must still survive a warp.

**The two verdicts that survive are as deliberate as the one that does not.**
`ShipCarriesNeitherCharge` is a fact about the ship's hold. `NoCrossoverDistance`
is this bot's third latch and #157 argues it out: #106 already spends the warp
boundary at the *evidence*, one hover per warp, so clearing the verdict would
re-latch it on the reading it was cleared on and buy nothing but the long
sentence reprinted once a warp. That is the tooltip/optimal-range hover family,
which is mission-runner-only on purpose, and this change deliberately does not
disturb it.

**Verified without a live client.** The transition is executed through the real
`Bot.elm` in `elm repl`, with readings built from the shape captured off the
live client during saxrat run 29 and run through the real
`EveOnline.ParseUserInterface` -- the same `WARP_READINGS` fixtures
`test_arrival_pilot_window.py` built for exactly this indication container. The
condition this replaces is executed on the same pair and asserted to answer
`False`, so a revert fails with the reason rather than an arithmetic mismatch
six rules away, and both consumers are run twice, once through each condition,
so the case is about the trigger rather than about the fixture.

Confirmed by mutation, each failing a named case:

  - restoring the old `Just False` condition in `weJustFinishedWarping` ->
    `TheOldConditionIsGone.test_weJustFinishedWarping_uses_the_shared_rule`.
  - restoring the inline maneuver pipeline in `shipIsWarping` ->
    `TheOldConditionIsGone.test_shipIsWarping_uses_the_shared_reader`.
  - restoring it inside this app's own copy of `warpJustEnded` ->
    `TheTransitionIsSeenOnTheClientsOwnShape.test_a_warp_ending_into_stillness_is_seen`,
    and the byte-identical drift check beside it.
  - dropping the `readingNow.shipUI /= Nothing` clause ->
    `test_a_reading_with_no_ship_ui_is_not_an_arrival`, and, separately,
    `TheDroneAbandonmentNowFiresOnTheWarpHalf
    .test_a_reading_with_no_ship_ui_is_not_a_departure`, which is the docking
    reading this bot actually produces.
  - `shipWarpingFromReading` reading `ManeuverJump` rather than `ManeuverWarp`
    -> `test_the_fixtures_parse_the_way_this_file_assumes`.
  - `ammoSwapGiveUpSurvivesAWarp` answering `True` for `GunsDidNotComeBack` ->
    `TheAmmoSwapGiveUpIsNowRetriedOnAWarp.test_the_disarm_give_up_is_cleared_when_a_warp_ends`.
  - it answering `False` for `NoCrossoverDistance`, which is the hover family
    being pulled across -> `test_the_other_two_give_ups_survive_the_warp`.
  - the drone rule no longer dropping the sighting when the verdict latches ->
    `test_the_sighting_is_dropped_so_the_dock_after_it_counts_once`.
  - the retry deciding for itself which verdicts a warp clears rather than
    asking `ammoSwapGiveUpSurvivesAWarp`, which is the sentence and the
    behaviour free to drift -> `test_the_sentence_and_the_retry_ask_one_rule`.
  - a decision consulting `dronesLeftBehind` ->
    `test_nothing_acts_on_the_verdict_it_writes`.
  - either consumer given its own second copy of the trigger ->
    `TheOldConditionIsGone.test_both_consumers_read_one_definition`.
  - the dead condition back in any app that carries the rule ->
    `TheThreeAppsCarryTheSameWorkingTrigger
    .test_no_app_still_carries_the_dead_condition`, which is what replaced
    #233's `TheMissionRunnerIsUntouched` and, in turn, absorbed
    `test_wingus_warp_end_trigger.TheFourAppsCarryTheSameWorkingTrigger` when
    that app was retired.

**Unverified: any of it running.** No run has been flown since, and neither
newly-live consumer has ever fired on the warp half in a recorded run -- by
construction, since the condition could not answer `True`. What to watch on the
first run that warps out of a pocket with drones in space is the decision log's
`Left drones behind:` line and then `LEFT BEHIND N at ...` in the status line;
on the first run whose ammo swap reaches `GunsDidNotComeBack`, the give-up
saying `off until the next warp` and then **going away** on the next warp with a
fresh `wants short-range for N reading(s)` after it. A drone-abandonment line on
a reading the ship merely docked would mean the ship-UI clause is not doing its
work, which is the one direction this must not fail in.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_BOT_ELM, SaxratRepl, source_of)
from test_arrival_pilot_window import (
    COMBAT_ANOMALY_BOT_ELM, WARP_READINGS, body_of_declaration,
    declaration_containing, indented_binding, record_returned_by,
    without_block_comments)

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The two declarations #201 built and #205 asks for here.
SHARED_DECLARATIONS = ("shipWarpingFromReading", "warpJustEnded")

# The dead condition, quoted from the issue and from the source every app
# carried it in. Matched without its parentheses, because two apps quote the
# shape in a doc comment and the code is what this is about -- the callers
# below strip block comments first.
OLD_CONDITION = "shipIsWarping == Just False"

# Every app that carries the working trigger, in the order they took it.
#
# There were four until `eve-online-wingus` was retired (see
# `notes/retire-wingus.md`); it took the rule in #233 and left with the last
# bot on the 2023 host interface. Nothing about the rule was wingus-specific,
# so its removal narrows the population and changes no assertion.
APPS_WITH_THE_RULE = (
    ("saxrat", SAXRAT_BOT_ELM),
    ("combat anomaly bot", COMBAT_ANOMALY_BOT_ELM),
    ("mission runner", MISSION_RUNNER_BOT_ELM),
)


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


# The two declarations that read `weJustFinishedWarping`, and the field each
# reads it into. Named here so a third reader arriving has to be added by
# somebody who has read what this change says the two do.
DRONE_ABANDONMENT_BINDING = "droneAbandonment"
AMMO_SWAP_FIELD = "justFinishedWarping = weJustFinishedWarping"

# What a run 11-shaped sighting looks like: five drones, seen at the place the
# ship warped *from*. The place is the sighting's rather than this reading's,
# which is the whole reason the count and the place are written down before the
# departure rather than read off the arrival.
STRANDED_COUNT = 5
SIGHTING_PLACE = "Irnin -- Illegal Activity (1 of 3)"
ARRIVAL_PLACE = "Mikhir -- Illegal Activity (2 of 3)"

# A `GunsDidNotComeBack` count in the shape run 11 recorded: the attempt ran one
# reading past `ammoSwapSilencedGiveUpTicks`.
DISARM_READINGS = 21


class MissionRunnerRepl(SaxratRepl):
    """The same harness and preamble as saxrat's, pointed at this bot.

    `reading_binding` is inherited unchanged: it is a pure builder over a JSON
    tree and the standard parser, naming nothing saxrat-specific, so the
    `WARP_READINGS` fixtures `test_arrival_pilot_window.py` built for the
    captured indication container can be handed to this repl as they stand.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "mission-runner-repl-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        super().__init__(**kwargs)


def elm_sighting(count, place):
    return 'Just { count = %d, place = "%s" }' % (count, place)


def abandonment(name, trigger):
    """A binding folding the real drone rule over a pair of real readings.

    `trigger` is the expression deciding `shipLeftThisReading`, given the
    previous reading as `b` and this one as `a`, so the same rule can be asked
    through the shipped condition and through the one it replaces without the
    fixtures moving underneath it.
    """
    return (
        "%s = \\before after -> Maybe.map2 (\\b a ->"
        " droneAbandonmentAfterReading"
        " { sightingBefore = %s"
        " , leftBehindBefore = Nothing"
        " , eventsBefore = 0"
        " , totalBefore = 0"
        " , dronesInSpaceNow = Just %d"
        ' , placeNow = "%s"'
        " , shipLeftThisReading = %s"
        " }) before after"
        % (name, elm_sighting(STRANDED_COUNT, SIGHTING_PLACE),
           STRANDED_COUNT, ARRIVAL_PLACE, trigger))


def give_up(name, trigger):
    """The same, for #154's retry: the real rule over a pair of real readings."""
    return (
        "%s = \\before after verdict -> Maybe.map2 (\\b a ->"
        " ammoSwapGiveUpAfterReading"
        " { before = Just verdict"
        " , reachedThisReading = Nothing"
        " , justFinishedWarping = %s"
        " }) before after" % (name, trigger))


# The shipped trigger and the one it replaces, written as expressions over the
# two readings so that every consumer case below can be asked through each.
SHIPPED_TRIGGER = ("warpJustEnded"
                   " { warpingLastReading = shipWarpingFromReading b"
                   ", readingNow = a }")
OLD_TRIGGER = ("(shipWarpingFromReading b == Just True)"
               " && (shipWarpingFromReading a == Just False)")

CONSUMER_BINDINGS = WARP_READINGS + (
    abandonment("abandonmentAcross", SHIPPED_TRIGGER),
    abandonment("oldAbandonmentAcross", OLD_TRIGGER),
    give_up("giveUpAcross", SHIPPED_TRIGGER),
    give_up("oldGiveUpAcross", OLD_TRIGGER),
    "leftBehindReported = describeDronesLeftBehind %s"
    % ("{ count = %d, place = \"%s\" }" % (STRANDED_COUNT, SIGHTING_PLACE)),
)


class TheThreeAppsCarryTheSameWorkingTrigger(unittest.TestCase):
    """One rule, in every app that carries it, and the dead shape in none.

    This is `test_wingus_warp_end_trigger.TheFourAppsCarryTheSameWorkingTrigger`
    relocated when `eve-online-wingus` was retired, merged with this file's own
    byte-identical check, which asserted exactly the first of its two halves.
    Its argument survives its subject and is why the case is moved rather than
    deleted: **what was worth noticing was never "wingus is behind"**, it is
    that several apps carry one rule that is app-specific in no part of it, and
    that a copy which drifts still compiles and still answers. So every app is
    compared byte for byte, and none of them may carry the shape #194 found
    dead. A further app growing its own copy, or one of the three drifting from
    the rest, goes red -- which makes a future divergence a decision somebody
    argues for rather than one the suite lets happen.

    That case itself replaced PR #233's `TheMissionRunnerIsUntouched`, which
    asserted this bot **still had** the dead condition and so collided with the
    change that fixed it. Two relocations, one property: the population moves,
    the rule does not.
    """

    def test_shipWarpingFromReading_and_warpJustEnded_are_byte_identical(self):
        for name in SHARED_DECLARATIONS:
            texts = {app: declaration(path, name)
                     for app, path in APPS_WITH_THE_RULE}
            distinct = set(texts.values())
            self.assertEqual(
                len(distinct), 1,
                "%s is not the same declaration in all %d apps -- they all "
                "compile and they all answer, so a drift here is silent. "
                "Lengths by app: %r"
                % (name, len(APPS_WITH_THE_RULE),
                   {app: len(text) for app, text in texts.items()}))

    def test_no_app_still_carries_the_dead_condition(self):
        """Block comments stripped, because two of the three quote the shape.

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


class TheOldConditionIsGone(unittest.TestCase):
    """`weJustFinishedWarping`'s own binding, read out of the source.

    Not an expression `elm repl` can be asked to evaluate on its own -- it is a
    `let` binding inside `updateMemoryForNewReadingFromGame` -- so it is read
    with the same indentation-sliced reader `test_arrival_pilot_window.py` uses
    for the equivalent binding in saxrat and the combat anomaly bot.
    """

    def setUp(self):
        self.source = without_block_comments(source_of(MISSION_RUNNER_BOT_ELM))
        self.update = body_of_declaration(
            self.source, "updateMemoryForNewReadingFromGame")

    def test_weJustFinishedWarping_uses_the_shared_rule(self):
        binding = indented_binding(self.update, "weJustFinishedWarping")
        self.assertIn(
            "warpJustEnded", binding,
            "the mission runner's weJustFinishedWarping no longer calls the "
            "shared warpJustEnded rule, which is #201's fix and the whole of "
            "the mission runner's half of #205")
        self.assertNotIn(
            "Just False", binding,
            "the mission runner's weJustFinishedWarping still spells out the "
            "unreachable Just False condition #194 and #205 are about -- "
            "restoring it is exactly the mutation this case exists to catch")

    def test_shipIsWarping_uses_the_shared_reader(self):
        """The inline pipeline is gone too, which is a drift closed.

        #201's own doc comment records that the apps derived this inline in two
        different shapes -- one a pipeline, one a `case` -- and calls that a
        drift that compiles. This bot had the pipeline; it now calls the one
        declaration, so the trigger and the memory field cannot come to
        disagree about what the client said.
        """
        binding = indented_binding(self.update, "shipIsWarping")
        self.assertIn(
            "shipWarpingFromReading", binding,
            "the mission runner derives shipIsWarping inline again instead of "
            "calling the shared reader, which is the drift #201 closed")
        self.assertNotIn(
            "ManeuverWarp", binding,
            "the inline maneuver read is back beside the shared one, so there "
            "are two answers to what the client named")

    def test_both_consumers_read_one_definition(self):
        """One trigger, two readers -- neither with a copy of its own.

        The mission runner's own comment beside the ammo swap says this in as
        many words: *the same `weJustFinishedWarping` the drone abandonment
        reads -- one definition, so the two cannot come to disagree about when
        a site ended*. A second copy would still compile and still answer.
        """
        drone = indented_binding(self.update, DRONE_ABANDONMENT_BINDING)
        self.assertIn(
            "shipLeftThisReading = weJustFinishedWarping", drone,
            "the drone abandonment no longer reads weJustFinishedWarping, so "
            "the half of shipLeftThisReading this change makes live is not "
            "wired to the fixed trigger")
        returned = record_returned_by(
            self.source, "updateMemoryForNewReadingFromGame")
        self.assertIn(
            AMMO_SWAP_FIELD, returned,
            "the ammo swap is no longer handed weJustFinishedWarping, so "
            "#154's per-warp retry is not wired to the fixed trigger")
        self.assertNotIn(
            "warpJustEnded", drone,
            "the drone abandonment has grown its own copy of the trigger "
            "beside the shared binding, which is two definitions of when a "
            "site ended")
        self.assertNotIn(
            "warpJustEnded", returned,
            "the returned record calls warpJustEnded directly rather than "
            "reading the one binding, which is two definitions of when a site "
            "ended")


class ExecutedAgainstTheRealBot:
    """One repl for this app, shared by the cases that execute rules."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(MissionRunnerRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()


class TheTransitionIsSeenOnTheClientsOwnShape(
        ExecutedAgainstTheRealBot, unittest.TestCase):
    """The transition itself, executed through this bot's own compiled code.

    The readings are the ones captured off the live client during saxrat run
    29: the ship UI's indication container is still present when a warp ends
    and holds only the location labels, no maneuver word. Nothing in the
    mission runner's source had ever been asked whether it notices that --
    every case that shipped with the dead condition asked about what happens
    *after* a departure, never about whether one is seen at all.
    """

    def test_the_fixtures_parse_the_way_this_file_assumes(self):
        answers = self.repl.evaluate(
            ["warpingIn warping == Just (Just True)",
             "shipUIPresentIn landed == Just True",
             "warpingIn orbiting == Just (Just False)",
             "shipUIPresentIn noShipUI == Just False"],
            WARP_READINGS)
        self.assertEqual(
            answers, [True] * 4,
            "the mission runner's parser does not make of these fixtures what "
            "this file assumes it does -- it vendors "
            "EveOnline.ParseUserInterface the same way every other app here "
            "does, and if that has drifted nothing below means anything")

    def test_the_transition_a_warp_makes_is_just_true_then_nothing(self):
        """The misreading that created the bug, pinned as a reading.

        `Just False` was read as *the ship is not warping*. It is not: it is
        the client naming some **other** maneuver. On the reading a warp ends
        the indication container is still there -- so this is not a reading
        that lost its ship UI -- and it names no maneuver at all, which the
        parser reads as `Nothing`. So the transition is `Just True -> Nothing`,
        and a condition demanding `Just False` was unreachable by construction.
        """
        answers = self.repl.evaluate(
            ["warpingIn warping == Just (Just True)",
             "warpingIn landed == Just Nothing",
             "indicationPresentIn landed == Just True",
             "warpingIn landed /= Just (Just False)"],
            WARP_READINGS)
        self.assertEqual(
            answers, [True] * 4,
            "the client's own warp-end reading no longer answers Nothing with "
            "its indication container present -- that pair is the whole of "
            "#194 and #205, and if it has changed the fix rests on nothing")

    def test_a_warp_ending_into_stillness_is_seen(self):
        """The case #194 and #205 are, and the one nothing had ever run."""
        answers = self.repl.evaluate(
            ["warpEndSeen warping landed == Just True"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "the mission runner does not notice a warp ending when the client "
            "stops naming a manoeuvre, which is what the client actually does "
            "-- so neither the drone abandonment's warp half nor #154's retry "
            "can fire")

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
            "the old Just False condition now answers True at the end of a "
            "warp, which the captured client reading says it cannot -- so "
            "this case is measuring something other than #194/#205")

    def test_a_warp_ending_into_another_maneuver_is_still_seen(self):
        """The one shape the old condition did handle, not lost in the fix."""
        answers = self.repl.evaluate(
            ["warpEndSeen warping orbiting == Just True"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "the mission runner no longer notices a warp that ends straight "
            "into another maneuver, which is the only end of warp the old "
            "condition could see")

    def test_a_reading_with_no_ship_ui_is_not_an_arrival(self):
        """The half of `Nothing` that must not count, and this bot docks.

        `shipWarpingFromReading` answers `Nothing` both for a ship that stopped
        manoeuvring and for a reading that could not see the ship at all. In
        the anomaly bots that second case is a client that did not render; here
        it is also the ordinary end of every trip, since a docked reading has
        no ship UI -- and `shipLeftThisReading`'s other half already fires on
        exactly that reading.
        """
        answers = self.repl.evaluate(
            ["warpEndSeen warping noShipUI == Just False"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "the mission runner treats a reading with no ship UI as a warp "
            "ending, so docking would be read as an arrival as well as a dock")

    def test_a_reading_still_in_warp_is_not_an_arrival(self):
        answers = self.repl.evaluate(
            ["warpEndSeen warping warping == Just False"], WARP_READINGS)
        self.assertEqual(
            answers, [True],
            "the mission runner calls every reading of a warp its end")

    def test_a_session_that_was_not_warping_before_is_not_an_arrival(self):
        """`Nothing -> Nothing` is not a warp ending either."""
        answers = self.repl.evaluate(
            ["warpEndSeen noShipUI landed == Just False",
             "warpEndSeen noShipUI noShipUI == Just False",
             "warpEndSeen landed landed == Just False"],
            WARP_READINGS)
        self.assertEqual(
            answers, [True] * 3,
            "the mission runner reads a session that has not warped as an "
            "arrival, which makes every reading one")


class TheDroneAbandonmentNowFiresOnTheWarpHalf(
        ExecutedAgainstTheRealBot, unittest.TestCase):
    """The first newly-live consumer, run rather than described.

    `shipLeftThisReading` is `weJustFinishedWarping || (dockedNow && not
    dockedInLastReading)`, and until now only the second half could ever be
    true. So the rule has been noticing drones left behind when the ship docks
    and never when it warps out of a pocket -- which is the case its own doc
    comment says it exists for. Every case here folds the real rule over the
    real captured readings, and the one below it runs the same rule through the
    condition this change replaces, so what separates them is the trigger and
    not the fixture.
    """

    def test_drones_in_space_when_a_warp_ends_are_recorded_as_left_behind(self):
        answers = self.repl.evaluate(
            ["Maybe.map .events (abandonmentAcross warping landed) == Just 1",
             "Maybe.map .total (abandonmentAcross warping landed) == Just %d"
             % STRANDED_COUNT,
             "Maybe.map (.leftBehind >> (/=) Nothing)"
             " (abandonmentAcross warping landed) == Just True",
             "Maybe.map .change (abandonmentAcross warping landed)"
             " == Just (Just leftBehindReported)"],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True] * 4,
            "a warp that ends with drones in space records no abandonment, so "
            "the half of #59's rule this change makes live is not live")

    def test_the_place_recorded_is_the_sightings_and_not_this_readings(self):
        """By the time the ship has arrived it is somewhere else.

        Both halves of *how many, and where* have to have been written down
        before the departure, which is why the rule reads `sightingBefore` for
        the place. Newly load-bearing: until now the only reading this fired on
        was a dock, where the arrival place is a station name rather than the
        pocket the drones are in.
        """
        answers = self.repl.evaluate(
            ['Maybe.map (.leftBehind >> Maybe.map .place)'
             ' (abandonmentAcross warping landed) == Just (Just "%s")'
             % SIGHTING_PLACE,
             'Maybe.map (.leftBehind >> Maybe.map .place)'
             ' (abandonmentAcross warping landed) /= Just (Just "%s")'
             % ARRIVAL_PLACE],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True] * 2,
            "the abandonment now names where the ship arrived rather than "
            "where it left the drones, which is the one thing the reading it "
            "fires on cannot see")

    def test_the_sighting_is_dropped_so_the_dock_after_it_counts_once(self):
        """The warp home and the dock that follows it are one event.

        The rule drops the sighting when the verdict latches, and that clause
        only starts mattering now: with the warp half dead there was never a
        latched verdict for a later dock to double-count against.
        """
        answers = self.repl.evaluate(
            ["Maybe.map (.sighting >> (==) Nothing)"
             " (abandonmentAcross warping landed) == Just True"],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True],
            "the sighting survives the verdict latching, so the dock after a "
            "warp home would report a second abandonment of the same drones")

    def test_the_condition_this_replaces_recorded_nothing(self):
        """The same rule, the same readings, the dead trigger."""
        answers = self.repl.evaluate(
            ["Maybe.map .events (oldAbandonmentAcross warping landed)"
             " == Just 0",
             "Maybe.map .change (oldAbandonmentAcross warping landed)"
             " == Just Nothing",
             "Maybe.map (.leftBehind >> (==) Nothing)"
             " (oldAbandonmentAcross warping landed) == Just True"],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True] * 3,
            "the condition this change replaces now records an abandonment at "
            "the end of a warp, so the two cases above are not separated by "
            "the trigger and this file is measuring the fixture")

    def test_a_reading_with_no_ship_ui_is_not_a_departure(self):
        """The docking reading, which the rule's *other* half already owns.

        This is the mission runner's own version of the ship-UI clause mattering:
        a fix written as `/= Just True` would make the ship's dock a warp
        ending too, and `shipLeftThisReading` would fire twice for one
        departure.
        """
        answers = self.repl.evaluate(
            ["Maybe.map .events (abandonmentAcross warping noShipUI)"
             " == Just 0"],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True],
            "a reading with no ship UI is recorded as a departure, so a dock "
            "reports the abandonment twice -- once for the missing ship UI "
            "and once for dockedNow")

    def test_a_reading_still_in_warp_is_not_a_departure(self):
        """Run 11 spent 21 readings of `I am in warp` getting its drones back."""
        answers = self.repl.evaluate(
            ["Maybe.map .events (abandonmentAcross warping warping)"
             " == Just 0"],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True],
            "a reading taken in warp is recorded as a departure, so a recall "
            "that lands before the warp finishes is reported as an "
            "abandonment that did not happen")

    def test_nothing_acts_on_the_verdict_it_writes(self):
        """A finding stated plainly, not a claim this change changes.

        #59 shipped the observation and nothing else: the rule acts on nothing
        and no decision consults it. That was cheap to hold while the warp half
        was dead. It is worth pinning now that the half is live, because this
        change makes the field move on readings it never moved on before, and a
        branch that started reading it would be a behaviour change with its own
        evidence to give.
        """
        source = without_block_comments(source_of(MISSION_RUNNER_BOT_ELM))
        readers = set()
        for index, line in enumerate(source.splitlines()):
            if "memory.dronesLeftBehind" not in line:
                continue
            owner = declaration_containing(source, index)
            if owner is not None:
                readers.add(owner)
        self.assertEqual(
            readers, {"missionBotDecisionRoot", "describeDronesLeftBehindSoFar"},
            "the mission runner reads dronesLeftBehind somewhere this change "
            "did not expect (%r) -- #59's rule reports and decides nothing, "
            "and a branch acting on it is a behaviour change with its own "
            "argument to make, not something these cases cover"
            % sorted(readers))


class TheAmmoSwapGiveUpIsNowRetriedOnAWarp(
        ExecutedAgainstTheRealBot, unittest.TestCase):
    """The second newly-live consumer, and the promise it makes good.

    #154 gave the disarm give-up a per-warp retry and the status line has said
    `off until the next warp` about it ever since -- on a trigger that could
    not fire, so the sentence was a promise the bot could not keep and the
    verdict stayed latched for the session. The rule is run here over the same
    captured readings, through the shipped trigger and through the one it
    replaces.
    """

    def test_the_disarm_give_up_is_cleared_when_a_warp_ends(self):
        answers = self.repl.evaluate(
            ["giveUpAcross warping landed (GunsDidNotComeBack %d)"
             " == Just Nothing" % DISARM_READINGS,
             "ammoSwapGiveUpSurvivesAWarp (GunsDidNotComeBack %d) == False"
             % DISARM_READINGS],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True] * 2,
            "a disarm give-up survives the end of a warp, so #154's retry is "
            "still dead and the status line's `off until the next warp` is "
            "still a promise the bot cannot keep")

    def test_the_condition_this_replaces_never_cleared_it(self):
        answers = self.repl.evaluate(
            ["oldGiveUpAcross warping landed (GunsDidNotComeBack %d)"
             " == Just (Just (GunsDidNotComeBack %d))"
             % (DISARM_READINGS, DISARM_READINGS)],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True],
            "the condition this change replaces now clears the give-up at the "
            "end of a warp, so the case above is not separated by the trigger")

    def test_the_other_two_give_ups_survive_the_warp(self):
        """Only the disarm verdict is retried, and #157 argues both the others.

        `ShipCarriesNeitherCharge` is a fact about the ship's hold that nothing
        short of docking alters. `NoCrossoverDistance` is the mission runner's
        own third latch and belongs to the tooltip/optimal-range hover family,
        which is deliberately mission-runner-only: #106 already spends the warp
        boundary at the evidence, one hover per warp, so retrying the *verdict*
        would re-latch it on the reading it was cleared on.
        """
        answers = self.repl.evaluate(
            ["giveUpAcross warping landed ShipCarriesNeitherCharge"
             " == Just (Just ShipCarriesNeitherCharge)",
             "giveUpAcross warping landed NoCrossoverDistance"
             " == Just (Just NoCrossoverDistance)",
             "ammoSwapGiveUpSurvivesAWarp ShipCarriesNeitherCharge == True",
             "ammoSwapGiveUpSurvivesAWarp NoCrossoverDistance == True"],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True] * 4,
            "a verdict that is not about one attempt is now retried once a "
            "warp -- for the crossover that is #106's evidence budget spent "
            "again for nothing, and for the hold it is a menu cascade per "
            "pocket answering the same thing every time")

    def test_a_reading_with_no_ship_ui_does_not_retry(self):
        answers = self.repl.evaluate(
            ["giveUpAcross warping noShipUI (GunsDidNotComeBack %d)"
             " == Just (Just (GunsDidNotComeBack %d))"
             % (DISARM_READINGS, DISARM_READINGS)],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True],
            "docking clears the disarm give-up, which is not a warp and is not "
            "the boundary #154 argued for")

    def test_a_reading_still_in_warp_does_not_retry(self):
        answers = self.repl.evaluate(
            ["giveUpAcross warping warping (GunsDidNotComeBack %d)"
             " == Just (Just (GunsDidNotComeBack %d))"
             % (DISARM_READINGS, DISARM_READINGS)],
            CONSUMER_BINDINGS)
        self.assertEqual(
            answers, [True],
            "every reading of a warp clears the disarm give-up, so the retry "
            "is once a reading rather than once a warp")

    def test_the_sentence_and_the_retry_ask_one_rule(self):
        """What an operator is told and what the bot does cannot drift.

        `ammoSwapGiveUpSurvivesAWarp` decides both, which is what makes the
        status line's `off until the next warp` a description of the retry
        rather than a second opinion about it.
        """
        source = without_block_comments(source_of(MISSION_RUNNER_BOT_ELM))
        readers = set()
        for index, line in enumerate(source.splitlines()):
            if "ammoSwapGiveUpSurvivesAWarp" not in line:
                continue
            owner = declaration_containing(source, index)
            if owner is not None and owner != "ammoSwapGiveUpSurvivesAWarp":
                readers.add(owner)
        self.assertIn(
            "ammoSwapGiveUpAfterReading", readers,
            "the retry no longer asks ammoSwapGiveUpSurvivesAWarp, so which "
            "verdicts a warp clears is decided somewhere the sentence cannot "
            "see (readers: %r)" % sorted(readers))
        self.assertTrue(
            len(readers) > 1,
            "nothing but the retry reads ammoSwapGiveUpSurvivesAWarp, so the "
            "status line is no longer deriving `off until the next warp` from "
            "the rule that decides it (readers: %r)" % sorted(readers))


if __name__ == "__main__":
    unittest.main()
