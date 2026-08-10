"""Tests for the mission runner's general guards, as they now stand in saxrat.

`eve-online-saxrat` is a combat bot: it flies into an anomaly, shoots rats and
comes back. Everything the mission runner learned about *the client and the
ship* -- as opposed to about missions, agents and stations -- applies to it
unchanged, and until this port it had almost none of it. What it had instead:

  - a retreat that compared the **live** HUD gauge against a threshold, with no
    low-water mark and no confirmation. That gauge is a float scraped out of a
    widget in the client's live memory and it produces values like 2132822% and
    a spurious 0%; the mission runner's run 11 printed forty retreat decisions
    on one such reading. saxrat would have done the same, and then oscillated,
    because a single live threshold has no hysteresis;
  - both hitpoint thresholds defaulting to `-1`, so in the shipped
    configuration there was **no retreat guard at all**;
  - no ship-loss detection, so a destroyed ship meant hunting anomalies in a
    capsule -- which reads 100% shield and 100% armour, so nothing above would
    have noticed either;
  - a drone recall with **no bound of any kind**, in front of every warp, every
    tether and every dock;
  - a target rule that was the overview's icon colour and nothing else, so
    anything the sprite palette did not cover was invisible even while shooting
    the ship.

These cases execute the ported rules through the real `Bot.elm` in `elm repl`
rather than restating them in Python, for the reason CLAUDE.md's "How a change
is verified here" gives: a Python restatement of a rule tests the restatement.
Where a rule takes a whole `ReadingFromGameClient`, the reading is built by
running a UI tree through the **real** `EveOnline.ParseUserInterface`, the way
`test_objective_chain_travel_step.py` does -- so a hand-written record cannot
drift from what the parser would actually have produced.

The wiring, the ordering and the counters' arithmetic -- which are not
expressions and cannot be evaluated -- are read out of the source instead,
through a whitespace-collapsing reader so an `elm-format` pass cannot break
them.

Confirmed by mutation. Each of these fails a named case: reading the live gauge
instead of the confirmed one, inverting `Maybe.map2 max` to `min`, removing the
low-water mark's re-arm level, letting an absent combat-log channel count as a
quiet grid, matching an attacker's name as a substring, dropping the on-grid
guard from the widened target rule, un-latching the ship-loss verdict, hoisting
the pod recovery below the docked-or-in-space split, removing the drone recall's
give-up, and counting that recall from the launch rather than from the ask.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import (ElmRepl, REPO_DIR, elm_json_literal,
                           elm_triple_quoted_json_literal, open_repl)

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")

# The capsule refusal, quoted verbatim from run 7's game log where it appears
# 173 times. There is no destruction line anywhere in the recorded logs; this is
# the consequence the client states instead, and only when something asks the
# capsule to lock.
CAPSULE_REFUSAL = (
    "The ship you are piloting does not have targeting systems installed.")

# Attacker names quoted from the recorded combat logs. Issue #40 rests on these
# being the same strings the overview shows: 33 of the 37 distinct attackers the
# combat log names appear byte for byte as an overview entry's Name, in the
# mission runner's own `Lock target from overview entry '...'` lines.
RECORDED_ATTACKERS = [
    "Centior Monster",
    "Federation Navy Delta II Support Frigate",
    "Kruul's Henchman",
    "R.S. Officer",
    "Centii Savage",
    "Tower Sentry Sansha I",
]

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    # The drone-recall cases build real effect values to ask
    # `recentStepAskedForDroneRecall` about, and `Bot exposing (..)` does not
    # re-export another module's constructors.
    "import Common.EffectOnWindow as EffectOnWindow",
)

_address = iter(range(100000, 999999))


def node(type_name, entries=None, children=(), region=None):
    """One UI tree node in the shape `decodeMemoryReadingFromString` wants."""
    dict_entries = dict(entries or {})
    if region is not None:
        x, y, width, height = region
        dict_entries.update({
            "_displayX": x, "_displayY": y,
            "_displayWidth": width, "_displayHeight": height,
        })
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": dict_entries,
        "children": list(children),
    }


def label(text, region):
    return node("EveLabelMedium", {"_name": "label", "_setText": text},
                region=region)


def game_log(entries):
    """The host's synthetic game-log node, exactly as `botlab_host.py` emits it.

    Note the text sits under `text`, never `_setText`: that is one of the four
    properties (CLAUDE.md, Architecture) that keep this fiction out of
    `getAllContainedDisplayTexts`, and the node carries no display region, so no
    region-navigating parser can reach it.
    """
    return node("MacOsHostSyntheticGameLog", {}, [
        node("MacOsHostSyntheticGameLogEntry",
             {"timestamp": "2026.08.03 04:27:33",
              "channel": channel, "text": text})
        for channel, text in entries])


def ship_ui(shield, armor, module_slots, structure=100):
    """A `ShipUI` the real parser will accept.

    It needs a `CapacitorContainer`, and its hitpoints need all three gauges by
    name -- `parseShipUIFromUITreeRoot` answers `Nothing` for hitpoints unless
    structure, armour and shield are all readable.
    """
    def gauge(name, percent):
        return node("Gauge", {"_name": name, "_lastValue": percent / 100.0},
                    region=(0, 0, 100, 8))

    slots = [
        node("ShipSlot", {"_name": "slot%d" % index}, [
            node("ModuleButton", {"_name": "modulebutton"},
                 region=(index * 40, 0, 32, 32)),
        ], region=(index * 40, 0, 32, 32))
        for index in range(module_slots)]

    return node("ShipUI", {}, [
        node("CapacitorContainer", {}, region=(0, 40, 100, 20)),
        gauge("structureGauge", structure),
        gauge("armorGauge", armor),
        gauge("shieldGauge", shield),
    ] + slots, region=(0, 0, 400, 200))


def overview(rows):
    """An overview window with Distance/Name/Type columns the parser can read.

    A header must span its cell (`parseListViewEntry`'s
    `headerRegionMatchesCellRegion`), which is why the column geometry here is
    explicit rather than incidental.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name, object_type) in enumerate(rows):
        y = 20 + index * 20
        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            label(distance, (10, y, 50, 16)),
            label(name, (110, y, 150, 16)),
            label(object_type, (310, y, 150, 16)),
        ], region=(0, y, 500, 16)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def tree_with(children):
    return node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def body_of(source, name):
    """One top-level declaration, from its type annotation to the next one."""
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


class SaxratRepl(ElmRepl):
    """The same harness, pointed at saxrat rather than the mission runner."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    @staticmethod
    def reading_binding(name, children):
        """A `let`-free binding of `name` to a real parsed reading.

        Goes through `decodeMemoryReadingFromString` and the real
        `parseUserInterfaceFromUITree`, so what the cases below assert on is
        what the bot would have been handed rather than a record shaped by hand.
        `Maybe.withDefault` is not available for a `ParsedUserInterface`, so the
        binding stays a `Maybe` and every expression maps over it.

        The literal comes from `elm_json_literal` rather than being written out
        here, because getting that wrong is not a broken fixture -- it is a case
        that passes having asserted against a reading that never arrived. See
        its doc comment.
        """
        return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
               " |> Result.toMaybe" \
               " |> Maybe.map EveOnline.ParseUserInterface" \
               ".parseUITreeWithDisplayRegionFromUITree" \
               " |> Maybe.map EveOnline.ParseUserInterface" \
               ".parseUserInterfaceFromUITree" % (
                   name, elm_json_literal(tree_with(children)))


class ReadingFixturesAreRealTest(unittest.TestCase):
    """The fixtures themselves, before anything is concluded from them.

    A case built on a tree the parser silently makes nothing of would pass or
    fail for reasons that have nothing to do with the rule under test -- so the
    trees are checked to parse into what they are meant to be first.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_trees_parse_into_the_readings_the_cases_assume(self):
        answers = self.repl.evaluate(
            ["(logged |> Maybe.andThen .gameLogEntriesSinceLastReading "
             "|> Maybe.map List.length) == Just 1",
             "(ship |> Maybe.map (.shipUI >> (/=) Nothing)) == Just True",
             "(ship |> Maybe.andThen .shipUI "
             "|> Maybe.map (.moduleButtons >> List.length)) == Just 4",
             "(ship |> Maybe.andThen .shipUI "
             "|> Maybe.map (.hitpointsPercent >> .shield)) == Just 40",
             "(rats |> Maybe.map (.overviewWindows >> List.concatMap .entries "
             ">> List.length)) == Just 2",
             "(empty |> Maybe.map (.shipUI >> (==) Nothing)) == Just True"],
            definitions=[
                self.repl.reading_binding(
                    "logged", [game_log([("notify", CAPSULE_REFUSAL)])]),
                self.repl.reading_binding("ship", [ship_ui(40, 90, 4)]),
                self.repl.reading_binding("rats", [overview([
                    ("5,000 m", "Centior Monster", "Centior Monster"),
                    ("6,000 m", "Centior Monster Wreck",
                     "Centior Monster Wreck")])]),
                self.repl.reading_binding("empty", []),
            ])
        self.assertEqual(
            answers, [True] * 6,
            "the parser does not make of these trees what the cases below "
            "assume it does, so nothing they conclude would mean anything")


class AFixtureRoundTripsWhateverJsonItIsHandedTest(unittest.TestCase):
    """Issue #174, and the case the eleven callers had no equivalent of.

    Every one of them checks what the parser made of a fixture. None checked
    that the fixture *arrived*, and those are different questions with the same
    answer: a reading that failed to decode is `Nothing`, which is also what a
    rule correctly answering nothing looks like. So a fixture the harness
    mangled produced passes rather than failures, in the direction this repo's
    cases exist to prevent.

    The text is this client's own route label, which is the fixture that made
    the defect visible: `alt="Next System in Route"`, in double quotes, against
    the 2019 recording's single ones.

    The control is the construction that was wrong, executed rather than
    described. `elm_json_literal`'s whole argument is that Elm processes
    backslash escapes inside a triple-quoted string, and a claim about the
    language that only a doc comment makes is one nobody notices going stale.
    """

    QUOTED_NAME = '<a href="showinfo:5//30005001" alt="Next System in Route">'

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def quoted_rows(self):
        return [("5,000 m", self.QUOTED_NAME, "Stargate (CONCORD System)")]

    def test_a_fixture_carrying_a_double_quote_reaches_the_parser(self):
        answers = self.repl.evaluate(
            ["(quoted |> Maybe.map (always True)) == Just True",
             "(quoted |> Maybe.map (.overviewWindows"
             " >> List.concatMap .entries >> List.length)) == Just 1"],
            definitions=[self.repl.reading_binding(
                "quoted", [overview(self.quoted_rows())])])
        self.assertEqual(
            answers, [True, True],
            "a fixture holding a double quote decoded to nothing, so every "
            "case built on one is asserting against a reading that never "
            "arrived")

    def test_the_text_comes_back_the_way_it_went_in(self):
        # Compared inside Elm against a plain `"..."` literal, which is a
        # different escaping path from the one under test, so the two cannot be
        # wrong together.
        answers = self.repl.evaluate(
            ["(quoted |> Maybe.map (.overviewWindows"
             " >> List.concatMap .entries >> List.filterMap .objectName"
             " >> (==) [ %s ])) == Just True" % json.dumps(self.QUOTED_NAME)],
            definitions=[self.repl.reading_binding(
                "quoted", [overview(self.quoted_rows())])])
        self.assertEqual(
            answers, [True],
            "the row's name did not survive the trip through the Elm literal")

    def test_the_triple_quoted_form_really_does_not_round_trip(self):
        mangled = (
            "mangled = EveOnline.MemoryReading.decodeMemoryReadingFromString"
            " %s |> Result.toMaybe" % elm_triple_quoted_json_literal(
                tree_with([overview(self.quoted_rows())])))
        answers = self.repl.evaluate(
            ["(mangled |> Maybe.map (always True)) == Nothing"],
            definitions=[mangled])
        self.assertEqual(
            answers, [True],
            "Elm no longer eats the backslashes inside a triple-quoted string, "
            "so `elm_json_literal`'s reason for encoding twice needs rewriting "
            "rather than deleting")


class HitpointConfirmationTest(unittest.TestCase):
    """One reading is not evidence -- executed, not described.

    The rule: `believed` is the healthier of the last two believable readings,
    so a drop has to survive a second look before the retreat, the low-water
    mark or the frozen-reading guard sees it. What it costs is one reading of
    delay on a real decline; what it buys is that a single corrupt reading
    changes nothing at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def gauge_after(self, readings, threshold=70):
        """Fold `readings` through `updateHitpointsGaugeMemory` one at a time.

        Each element is an Elm expression for a `Maybe Int` -- `Just 95` for a
        believable reading, `Nothing` for one there was no ship UI for or that
        `plausibleHitpointsPercent` rejected.
        """
        folded = "initHitpointsGaugeMemory"
        for reading in readings:
            folded = "updateHitpointsGaugeMemory %d (%s) (%s)" % (
                threshold, reading, folded)
        return folded

    def test_plausible_percent_rejects_the_recorded_garbage(self):
        """The values the gauge really produced, through the real filter.

        Every one of these is from a recorded run, each for exactly one reading
        and each surrounded by sane values.
        """
        recorded = [-1021821, 2132822, 302023, 8362, 7711, 385]
        legal = [0, 1, 50, 99, 100]
        answers = self.repl.evaluate(
            ["plausibleHitpointsPercent (%d) == Nothing" % value
             for value in recorded]
            + ["plausibleHitpointsPercent %d == Just %d" % (value, value)
               for value in legal])
        self.assertEqual(answers, [True] * (len(recorded) + len(legal)))

    def test_a_single_corrupt_zero_is_never_believed(self):
        """Run 11's shape: 96, 96, 0, 96 against an armour threshold of 70.

        The raw gauge trips on the third reading; `believed` never leaves 96,
        because a `0` bracketed by healthy readings is never the healthier of
        any two consecutive ones. That reading is the one the mission runner
        printed `Armor reached 0%` on forty times with the armour at 82-96%.
        """
        answers = self.repl.evaluate([
            "(%s).believed == Just 96" % self.gauge_after(prefix)
            for prefix in [["Just 96", "Just 96"],
                           ["Just 96", "Just 96", "Just 0"],
                           ["Just 96", "Just 96", "Just 0", "Just 96"]]])
        self.assertEqual(
            answers, [True] * 3,
            "a single 0 between healthy readings reached `believed`")

    def test_a_real_decline_is_delayed_by_one_reading_not_suppressed(self):
        """`75, 70, 65, 60` -- a hull genuinely losing armour.

        `believed` tracks one reading behind, so the retreat fires one reading
        later than the raw gauge would have and never fails to fire. That is
        the cost of the rule, asserted rather than assumed.
        """
        declining = ["Just 75", "Just 70", "Just 65", "Just 60"]
        answers = self.repl.evaluate([
            "(%s).believed == Just %d" % (
                self.gauge_after(declining[:index + 1]), expected)
            for index, expected in enumerate([75, 75, 70, 65])])
        self.assertEqual(
            answers, [True] * 4,
            "the believed value should lag a declining gauge by exactly one "
            "reading -- never more, which would be a suppression")

    def test_a_gap_in_the_gauge_is_not_agreement_across_it(self):
        """`Just 90, Nothing, Just 10` must believe 10, not 90.

        `Maybe.map2` is what makes this work: an unbelievable reading, or one
        with no ship UI at all, leaves nothing behind for the next reading to
        confirm against. Without it the readings either side of a gap would
        vouch for each other.
        """
        [believed_ten] = self.repl.evaluate([
            "(%s).believed == Just 10"
            % self.gauge_after(["Just 90", "Nothing", "Just 10"])])
        self.assertTrue(
            believed_ten,
            "readings either side of a gauge gap were treated as agreement "
            "across it")

    def test_a_withheld_reading_is_counted_and_kept(self):
        """The status line's evidence that the gauge has started lying.

        Counted only where the reading would have tripped *this gauge's* own
        threshold, so a gauge nobody is reading reports nothing. That matters
        more here than in the mission runner, since saxrat ships both hitpoint
        thresholds at `-1`.
        """
        withheld = self.gauge_after(["Just 96", "Just 0"], threshold=70)
        disabled = self.gauge_after(["Just 96", "Just 0"], threshold=-1)
        counted, remembered, silent = self.repl.evaluate([
            "(%s).readingsWithheld == 1" % withheld,
            "(%s).lastWithheld == Just 0" % withheld,
            "(%s).readingsWithheld == 0" % disabled,
        ])
        self.assertTrue(counted, "the withheld reading was not counted")
        self.assertTrue(remembered, "the withheld value was not kept")
        self.assertTrue(
            silent,
            "a gauge whose threshold is disabled reported a withheld reading, "
            "but nothing is reading it")

    def test_the_low_water_mark_holds_until_recovery_or_docking(self):
        """`lowWaterMark`, which saxrat had no equivalent of at all.

        Three behaviours, and the third is what ends the oscillation a single
        live threshold produces: a mark set below the re-arm level is kept even
        while the gauge reads higher, so a retreat stays committed instead of
        flipping back the moment a repairer catches up.
        """
        answers = self.repl.evaluate(
            [# Docked -- no ship UI -- forgets outright.
             "(docked |> Maybe.map (\\r -> lowWaterMark r (Just 20) 20)) "
             "== Just 100",
             # At or above the re-arm level, forget.
             "(inSpace |> Maybe.map (\\r -> lowWaterMark r "
             "(Just runAwayRearmPercent) 20)) == Just 100",
             # Below it, keep the lowest seen -- even while the gauge recovers
             # part of the way.
             "(inSpace |> Maybe.map (\\r -> lowWaterMark r (Just 80) 20)) "
             "== Just 20",
             "(inSpace |> Maybe.map (\\r -> lowWaterMark r (Just 10) 20)) "
             "== Just 10",
             # An unbelievable reading moves nothing.
             "(inSpace |> Maybe.map (\\r -> lowWaterMark r Nothing 20)) "
             "== Just 20"],
            definitions=[
                self.repl.reading_binding("docked", []),
                self.repl.reading_binding("inSpace", [ship_ui(50, 90, 4)]),
            ])
        self.assertEqual(answers, [True] * 5)

    def test_the_rearm_level_sits_above_every_sane_threshold(self):
        """A re-arm level at or below a trip level would never release."""
        [above] = self.repl.evaluate(["runAwayRearmPercent == 90"])
        self.assertTrue(above)


class IncomingDamageTest(unittest.TestCase):
    """The guard that needs no gauge, and the distinction it must keep.

    `Nothing` from the parser means this host does not carry the client's combat
    log; `Just { damage = 0 }` means the client reported no incoming fire. Only
    the second may ever be read as a quiet grid, and reading the first that way
    is this repo's signature failure.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    SAMPLE = ("\\ms damage attacker -> "
              "{ atMilliseconds = ms, damage = damage, "
              "hitpoints = Nothing, attacker = attacker }")

    def test_the_window_sums_and_names_what_hit_us(self):
        memory = ("{ samples = "
                  "[ sample 3000 100 (Just \"Centior Monster\")"
                  ", sample 2000 200 (Just \"R.S. Officer\")"
                  ", sample 1000 300 (Just \"Centior Monster\")"
                  " ], hostCarriesTheChannel = True"
                  ", lastAttacker = Nothing, retreating = False }")
        summed, named = self.repl.evaluate(
            ["incomingDamageInWindow memory == 600",
             "List.sort (namesOfRecentAttackers memory) "
             "== [ \"Centior Monster\", \"R.S. Officer\" ]"],
            definitions=["sample = " + self.SAMPLE, "memory = " + memory])
        self.assertTrue(summed, "the window did not sum its samples")
        self.assertTrue(
            named,
            "the attacker names were not deduplicated across the window")

    def test_a_frozen_reading_needs_enough_readings_to_mean_anything(self):
        """`Nothing` while the window is short, and `Nothing` samples never
        count as movement -- so a window of unreadable values reads as frozen,
        which is the conservative direction and the intended one."""
        def memory(hitpoints):
            samples = ", ".join(
                "{ atMilliseconds = %d, damage = 10, hitpoints = %s, "
                "attacker = Nothing }" % (index * 1000, value)
                for index, value in enumerate(hitpoints))
            return ("{ samples = [ %s ], hostCarriesTheChannel = True, "
                    "lastAttacker = Nothing, retreating = False }" % samples)

        answers = self.repl.evaluate([
            "hitpointsReadingMovedInWindow (%s) == Nothing"
            % memory(["Just ( 100, 100 )"] * 3),
            "hitpointsReadingMovedInWindow (%s) == Just False"
            % memory(["Just ( 100, 100 )"] * 5),
            "hitpointsReadingMovedInWindow (%s) == Just False"
            % memory(["Nothing"] * 5),
            "hitpointsReadingMovedInWindow (%s) == Just False"
            % memory(["Just ( 100, 100 )"] * 4 + ["Nothing"]),
            "hitpointsReadingMovedInWindow (%s) == Just True"
            % memory(["Just ( 100, 100 )"] * 4 + ["Just ( 90, 100 )"]),
        ])
        self.assertEqual(answers, [True] * 5)

    def test_an_absent_channel_is_reported_rather_than_read_as_quiet(self):
        source = source_of(SAXRAT_BOT_ELM)
        update = collapsed(body_of(source, "updateIncomingDamageMemory"))
        self.assertIn(
            "hostCarriesTheChannel = context.readingFromGameClient"
            ".incomingDamageSinceLastReading /= Nothing", update,
            "the memory no longer records whether the host carries the channel")
        self.assertIn(
            "case context.readingFromGameClient.incomingDamageSinceLastReading "
            "of Nothing -> keptSamples", update,
            "an absent channel must leave the window alone, never append a "
            "zero that reads as a quiet grid")

        describe = collapsed(body_of(source, "describeIncomingDamage"))
        self.assertIn(
            "NO COMBAT LOG", describe,
            "the status line no longer says when this guard is unarmed, which "
            "is the only thing that makes reading its silence safe")

    def test_the_latch_releases_on_absence_not_on_recovery(self):
        """Trip and release are different conditions on purpose: the moment the
        ship warps clear the window starts draining, so a live comparison would
        cancel its own retreat halfway through."""
        update = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "updateIncomingDamageMemory"))
        self.assertIn(
            "retreating = if damageInWindow <= 0 then False else if "
            "0 <= threshold && threshold <= damageInWindow then True else "
            "memoryBefore.retreating", update,
            "the retreat latch is no longer released only by an empty window")

    def test_the_calibrated_constants_are_where_the_measurements_put_them(self):
        """Each of these is a number about a hull with evidence behind it, so a
        change to one is a change with its own argument to make."""
        answers = self.repl.evaluate([
            "defaultRunAwayIncomingDamageThreshold == 3500",
            "incomingDamageWindowSeconds == 45",
            "damageThatMustMoveTheHitpointsReading == 1500",
            "readingsBeforeAFrozenHitpointsReadingCounts == 4",
            "damageThatMustMoveTheHitpointsReading "
            "< defaultRunAwayIncomingDamageThreshold",
        ])
        self.assertEqual(
            answers, [True] * 5,
            "a retreat constant moved off its measured value, or the "
            "frozen-reading guard stopped being the more patient of the two")

    def test_the_threshold_is_on_by_default_where_the_gauges_are_not(self):
        """Why this guard matters more here than where it was measured: saxrat
        ships both hitpoint thresholds disabled, so before this port its shipped
        configuration had no retreat at all."""
        defaults = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                     "defaultBotSettings"))
        self.assertIn("runAwayShieldHitpointsThresholdPercent = -1", defaults)
        self.assertIn("runAwayArmorHitpointsThresholdPercent = -1", defaults)
        self.assertIn(
            "runAwayIncomingDamageThreshold = "
            "defaultRunAwayIncomingDamageThreshold", defaults,
            "the one guard that is armed by default is no longer armed by "
            "default")

    def test_the_setting_is_parsed_and_can_be_disabled(self):
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn('( "run-away-incoming-damage-threshold"', source,
                      "the threshold is no longer settable")
        self.assertIn("run-away-incoming-damage-threshold`: Hitpoints", source,
                      "the setting is no longer documented in the bot's own "
                      "header, which is what `bot_help.py` reports")


class ShootBackAtAttackersTest(unittest.TestCase):
    """Whatever the client says is shooting the ship is a valid target.

    saxrat's rule was the overview's icon colour alone -- a sprite palette test,
    so it requires the palette to have covered the object. When it does not, the
    bot prints "Rats in overview: 0" while its armour drains, which reads
    exactly like a clear grid.

    The rows below come from the real parser, so what these cases match against
    is what a reading would actually have carried.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    @staticmethod
    def rows_binding(name, overviewWindow):
        """The entries of one overview window, as the real parser reads them.

        `tree_with` takes the root's *children*, so the window has to be
        wrapped in a list. Passing the node bare makes `list()` iterate its
        keys, the tree fails to decode, and every case built on it then asks
        its question of an empty list of rows -- which answers `False` to
        anything, so the cases expecting `False` pass while testing nothing.
        """
        return SaxratRepl.reading_binding(name + "Reading", [overviewWindow]) \
            + "\n%s = %sReading |> Maybe.map (.overviewWindows >> " \
              "List.concatMap .entries) |> Maybe.withDefault []" % (name, name)

    def named_rows(self, name, names):
        """One overview row per name, at a distance that parses in meters."""
        return self.rows_binding(
            name, overview([("%d m" % (1000 + index * 10), value, value)
                            for index, value in enumerate(names)]))

    def test_the_recorded_attacker_names_match_their_overview_rows(self):
        """Byte for byte, apostrophes and full stops intact."""
        answers = self.repl.evaluate(
            ['List.any (isObjectShootingAtUs [ "%s" ]) attackers' % name
             for name in RECORDED_ATTACKERS],
            definitions=[self.named_rows("attackers", RECORDED_ATTACKERS)])
        self.assertEqual(
            answers, [True] * len(RECORDED_ATTACKERS),
            "an attacker the combat log named did not match the overview row "
            "the bot's own decision lines print for it")

    def test_a_wreck_is_not_the_thing_that_was_shooting_us(self):
        """The reason the match is exact rather than a substring.

        A wreck's Type is its owner's name with " Wreck" appended. A substring
        rule would have the bot open fire on the corpse of the thing that just
        stopped shooting it -- forever, since a wreck cannot die.
        """
        traps = ["Centior Monster Wreck", "Kruul's Pleasure Hub",
                 "R.S. Officer Wreck"]
        answers = self.repl.evaluate(
            ['List.any (isObjectShootingAtUs [ "%s" ]) traps' % attacker
             for attacker in ["Centior Monster", "Kruul", "R.S. Officer"]]
            + ["List.any (isObjectShootingAtUs []) traps"],
            definitions=[self.named_rows("traps", traps)])
        self.assertEqual(
            answers, [False] * 4,
            "an attacker name matched as a substring, which selects wrecks and "
            "unrelated objects that merely contain it -- or an empty attacker "
            "set, which is what both a quiet grid and a host with no combat "
            "log arrive here as, widened the target set")

    def test_matching_ignores_case_and_surrounding_space(self):
        answers = self.repl.evaluate(
            ['List.any (isObjectShootingAtUs [ "  centior monster " ]) rats',
             'List.any (isObjectShootingAtUs [ "CENTIOR MONSTER" ]) rats'],
            definitions=[self.named_rows("rats", ["Centior Monster"])])
        self.assertEqual(
            answers, [True] * 2,
            "the match should not depend on the client's capitalisation")

    def test_the_widened_rule_still_excludes_an_au_distance(self):
        """An entry that qualifies only because it shot us enters the same list
        at its own distance rank and is subject to every guard the colour rule's
        entries are. An AU distance does not parse as meters, and nothing
        measured in AU is reachable in combat."""
        far = overview([("14.7 AU", "Centior Monster", "Centior Monster")])
        near = overview([("5,000 m", "Centior Monster", "Centior Monster")])
        answers = self.repl.evaluate(
            ['List.any (shouldAttackOverviewEntry [ "Centior Monster" ]) near',
             'List.any (shouldAttackOverviewEntry [ "Centior Monster" ]) far'],
            definitions=[self.rows_binding("far", far),
                         self.rows_binding("near", near)])
        self.assertEqual(
            answers, [True, False],
            "the on-grid guard no longer applies to an entry that qualified by "
            "having shot us")

    def test_the_rule_is_a_disjunction_gated_by_distance(self):
        rule = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "shouldAttackOverviewEntry"))
        self.assertRegex(
            rule,
            r"\(\s*iconSpriteHasColorOfRat overviewEntry \|\| "
            r"isObjectShootingAtUs attackerNames overviewEntry\s*\) && "
            r"overviewEntryDistanceIsOnGrid overviewEntry",
            "the colour rule, the attacker rule and the on-grid guard are no "
            "longer one disjunction gated by distance")

    def test_the_names_are_passed_in_rather_than_read_from_memory(self):
        """So the caller that folds this reading into the window first can pass
        the window that includes it, rather than the previous reading's."""
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        for name in ("overviewEntriesToAttackFromReadingFromGameClient",
                     "anyAttackableInOverview", "shouldAttackOverviewEntry"):
            self.assertIn(
                "%s : List String ->" % name, source,
                "%s no longer takes the attacker names as an argument" % name)


class ShipLossTest(unittest.TestCase):
    """A capsule reads 100% shield and 100% armour, so nothing above notices.

    The two signals that survived contact with the recordings, and the latch
    that stops the verdict being un-concluded by a later reading that happens to
    look normal.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_matcher_is_the_sentence_the_client_really_wrote(self):
        """Run 7's line, and the refusals that must not be mistaken for it."""
        answers = self.repl.evaluate(
            ["(capsule |> Maybe.map (shipLossFromGameLog >> (/=) Nothing)) "
             "== Just True",
             "(ammo |> Maybe.map (shipLossFromGameLog >> (==) Nothing)) "
             "== Just True",
             "(noLog |> Maybe.map (shipLossFromGameLog >> (==) Nothing)) "
             "== Just True",
             # The channel matters: three consumers here read `notify`, and a
             # filter on the wrong channel is a guard that can never fire.
             "(onInfo |> Maybe.map (shipLossFromGameLog >> (==) Nothing)) "
             "== Just True"],
            definitions=[
                self.repl.reading_binding(
                    "capsule", [game_log([("notify", CAPSULE_REFUSAL)])]),
                self.repl.reading_binding("ammo", [game_log([
                    ("notify", "You cannot load or unload Focused Modulated "
                               "Medium Energy Beam I while it is active.")])]),
                self.repl.reading_binding("noLog", []),
                self.repl.reading_binding(
                    "onInfo", [game_log([("info", CAPSULE_REFUSAL)])]),
            ])
        self.assertEqual(
            answers, [True] * 4,
            "the capsule refusal is not matched as the client writes it, or an "
            "unrelated refusal was read as a ship loss")

    def test_the_module_signal_needs_a_ship_ui_and_several_readings(self):
        """A docked reading has no ship UI and is no evidence either way, so it
        must not accumulate towards a verdict."""
        answers = self.repl.evaluate(
            ["(docked |> Maybe.map shipUIHasNoModuleButtons) == Just False",
             "(capsule |> Maybe.map shipUIHasNoModuleButtons) == Just True",
             "(ship |> Maybe.map shipUIHasNoModuleButtons) == Just False",
             "(docked |> Maybe.map (\\r -> "
             "shipUIWithoutModuleButtonsReadingsAfter r 2)) == Just 0",
             "(ship |> Maybe.map (\\r -> "
             "shipUIWithoutModuleButtonsReadingsAfter r 2)) == Just 0",
             "(capsule |> Maybe.map (\\r -> "
             "shipUIWithoutModuleButtonsReadingsAfter r 2)) == Just 3",
             "shipLossReadingsWithoutModulesBeforeVerdict == 3"],
            definitions=[
                self.repl.reading_binding("docked", []),
                self.repl.reading_binding("capsule", [ship_ui(100, 100, 0)]),
                self.repl.reading_binding("ship", [ship_ui(100, 100, 4)]),
            ])
        self.assertEqual(answers, [True] * 7)

    def test_a_capsule_reads_fully_healthy_which_is_why_this_exists(self):
        """The premise of the whole guard, taken from the parser rather than
        asserted: nothing about the hitpoints of a capsule says anything is
        wrong, so no threshold on them could ever have caught this."""
        [healthy] = self.repl.evaluate(
            ["(capsule |> Maybe.andThen .shipUI "
             "|> Maybe.map (\\ui -> ui.hitpointsPercent.shield == 100 "
             "&& ui.hitpointsPercent.armor == 100)) == Just True"],
            definitions=[
                self.repl.reading_binding("capsule", [ship_ui(100, 100, 0)])])
        self.assertTrue(healthy)

    def test_the_verdict_latches_and_counts_its_readings(self):
        """Once set it is returned unchanged forever, with only its age moving.

        This is the cost asymmetry written into the code: docking early costs
        the rest of the session, and un-concluding a loss costs the clone.
        """
        latched = '(Just { reason = "already known", readingsSince = 7 })'
        answers = self.repl.evaluate(
            ["(quiet |> Maybe.map (\\r -> shipLossVerdictAfter r "
             "{ withoutModulesReadings = 0, verdictBefore = %s })) "
             "== Just (Just { reason = \"already known\", readingsSince = 8 })"
             % latched,
             # Below the threshold, with nothing in the log, no verdict.
             "(quiet |> Maybe.map (\\r -> shipLossVerdictAfter r "
             "{ withoutModulesReadings = 2, verdictBefore = Nothing })) "
             "== Just Nothing",
             # At it, a verdict, freshly aged.
             "(quiet |> Maybe.map (\\r -> shipLossVerdictAfter r "
             "{ withoutModulesReadings = 3, verdictBefore = Nothing } "
             "|> Maybe.map .readingsSince)) == Just (Just 0)",
             # The game log alone is enough, with the module count at zero.
             "(capsule |> Maybe.map (\\r -> shipLossVerdictAfter r "
             "{ withoutModulesReadings = 0, verdictBefore = Nothing } "
             "|> Maybe.map .readingsSince)) == Just (Just 0)"],
            definitions=[
                self.repl.reading_binding("quiet", [game_log([])]),
                self.repl.reading_binding(
                    "capsule", [game_log([("notify", CAPSULE_REFUSAL)])]),
            ])
        self.assertEqual(
            answers, [True] * 4,
            "the ship-loss verdict no longer latches, no longer counts the "
            "readings its recovery is bounded by, or no longer fires on the "
            "client's own sentence")

    def test_the_recovery_sits_above_the_docked_or_in_space_split(self):
        """Placement, not a condition, is what makes "stop fighting"
        structural: locking, drones, modules and looting all live below the
        split and are simply never reached."""
        root = collapsed(body_of(
            source_of(SAXRAT_BOT_ELM),
            "anomalyBotDecisionRootBeforeApplyingSettings"))
        self.assertLess(
            root.index("recoverPodAfterShipLoss context"),
            root.index("branchDependingOnDockedOrInSpace"),
            "the pod recovery must be reached before anything that fights")

    def test_the_recovery_is_bounded_and_the_bound_ends_the_session(self):
        """Every way this can fail runs under one clock, so none of them can
        become a forever-loop -- issues #7 and #14 twice over.

        Since #133 the comparison is asked from `podRecoveryOutOfTime` at the
        head of the decision root rather than from inside this branch, which is
        what makes the clock reachable on a reading something above holds the
        tree. `test_saxrat_pod_recovery_deadline_reachable.py` owns that; what
        this case still pins is that the bound exists and that the one outcome
        left here -- the pod docked -- still ends the session.
        """
        recovery = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                     "recoverPodAfterShipLoss"))
        self.assertNotIn(
            "podRecoveryGiveUpReadings", recovery,
            "the deadline is back inside the branch a held tree cannot reach")
        self.assertEqual(
            1, recovery.count(
                "Common.DecisionPath.endDecisionPath FinishSession"),
            "the docked outcome must still end the session -- the remaining "
            "hours are worth nothing without a ship")
        [bound] = self.repl.evaluate(["podRecoveryGiveUpReadings == 150"])
        self.assertTrue(bound)


class DroneRecallBoundTest(unittest.TestCase):
    """A recall that never lands, in front of every warp, tether and dock.

    saxrat's `returnDronesToBay` had no counter of any kind: Shift+R went out on
    every reading for as long as the drones stayed in space, and nothing in the
    reading ever says whether the client took the keypress.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def counter_source(self):
        update = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "updateMemoryForNewReadingFromGame"))
        counter = update[update.index("droneRecallUnansweredTicks ="):]
        return counter[:counter.index("dronesInSpaceCountLastReading =")]

    def test_the_ask_is_recognised_by_the_key_it_presses(self):
        """`vkey_R` is used for nothing else in this bot. `vkey_E` is the
        approach chord and `vkey_W` the orbit, so neither may match."""
        recall = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.KeyDown EffectOnWindow.vkey_R ]")
        approach = "[ EffectOnWindow.KeyDown EffectOnWindow.vkey_E ]"
        orbit = "[ EffectOnWindow.KeyDown EffectOnWindow.vkey_W ]"
        answers = self.repl.evaluate([
            "recentStepAskedForDroneRecall [ %s ]" % recall,
            "recentStepAskedForDroneRecall [ %s ] == False" % approach,
            "recentStepAskedForDroneRecall [ %s ] == False" % orbit,
            "recentStepAskedForDroneRecall [] == False",
            # Looked for across a window, because the focus-recovery branch
            # alternates click and keypress.
            "recentStepAskedForDroneRecall [ %s, %s ]" % (approach, recall),
            # But not beyond it, so a bot that went back to fighting stops
            # counting readings against a recall nobody is making.
            "recentStepAskedForDroneRecall [ %s, %s, %s, %s ] == False"
            % (approach, approach, approach, recall),
        ])
        self.assertEqual(answers, [True] * 6)

    def test_the_counter_starts_at_the_ask_and_never_at_the_launch(self):
        """The whole of issue #11. Drones are deliberately left out for a fight,
        so a counter started at launch reaches any threshold during an ordinary
        engagement -- after which the recall declines for the rest of the
        session and every warp abandons whatever is in space."""
        counter = self.counter_source()
        self.assertIn(
            "recentStepAskedForDroneRecall context.previousStepsEffects",
            counter, "the unanswered counter no longer advances on the ask")
        self.assertNotIn(
            "dronesInSpaceTicks", counter,
            "the unanswered counter must not be derived from how long the "
            "drones have been out -- that is the launch, not the ask")
        self.assertIn(
            "if dronesInSpaceCountNow < 1 then 0", counter,
            "the counter no longer clears when the drones are home")
        self.assertIn(
            "else if dronesInSpaceCountNow < "
            "botMemoryBefore.dronesInSpaceCountLastReading then 0", counter,
            "a partial recall is the client answering and must reset the "
            "patience")
        self.assertIn(
            "else if droneRecallGiveUpTicks < "
            "botMemoryBefore.droneRecallUnansweredTicks then "
            "botMemoryBefore.droneRecallUnansweredTicks", counter,
            "past the give-up the counter must hold rather than reset -- "
            "giving up is what stops the asking, so a reset would unwind it "
            "and the ship would alternate forever")

    def test_the_counter_can_actually_reach_its_bound(self):
        """The mutation `test_ammo_silenced_bound` was written to catch: a
        counter pinned at a constant satisfies "it is mentioned"."""
        self.assertIn(
            "botMemoryBefore.droneRecallUnansweredTicks + 1",
            self.counter_source(),
            "the counter never advances, so its bound is unreachable")

    def test_the_give_up_names_itself_every_time_it_declines(self):
        """A give-up that returns nothing at all is one an operator cannot see,
        and the log then reads exactly like a bot that never had drones out.
        That is why this takes a continuation rather than returning a `Maybe`.
        """
        source = source_of(SAXRAT_BOT_ELM)
        self.assertIn(
            "returnDronesToBay : BotDecisionContext -> DecisionPathNode "
            "-> DecisionPathNode", collapsed(source),
            "returnDronesToBay no longer hands the caller's next step on, so "
            "the branch that abandons the drones cannot name itself")

        recall = collapsed(body_of(source, "returnDronesToBay"))
        self.assertIn(
            "else if droneRecallGiveUpTicks < "
            "context.memory.droneRecallUnansweredTicks then", recall,
            "the recall is no longer bounded")
        self.assertIn(
            "will not come back -- leave without them", recall,
            "the give-up no longer says so in the decision log")
        self.assertIn(
            "droneRecallFocusRecoveryTicks < context.memory.dronesInSpaceTicks",
            recall,
            "the focus-recovery click is gone -- Shift+R does nothing at all "
            "when the client is not taking keyboard input, and nothing in the "
            "reading says so")

    def test_no_caller_can_silently_drop_the_recall(self):
        """Every call site hands a real next step on, so a `Maybe.withDefault`
        left over from the old shape is a compile error rather than a recall
        that quietly does nothing."""
        self.assertNotIn("returnDronesToBay context |> Maybe",
                         collapsed(source_of(SAXRAT_BOT_ELM)))

    def test_the_counters_are_reported_before_the_give_up_is_reached(self):
        describe = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                     "describeDroneRecall"))
        self.assertIn("droneRecallUnansweredTicks", describe)
        self.assertIn("GIVEN UP", describe,
                      "an operator cannot see the recall has been abandoned")


class FrameworkParityTest(unittest.TestCase):
    """The two apps' copies of the shared framework, which now agree.

    CLAUDE.md recorded `previousStepsEffects` as a mission-runner-only
    divergence. It is not app-specific -- a counter that has to measure how long
    ago the bot *asked* for something cannot be derived from the reading alone,
    and saxrat's drone recall is exactly that shape -- so the port closes the
    divergence rather than widening it.
    """

    FRAMEWORK = os.path.join("EveOnline", "BotFrameworkSeparatingMemory.elm")

    def test_saxrat_and_the_mission_runner_share_one_framework(self):
        self.assertEqual(
            source_of(os.path.join(SAXRAT_DIR, self.FRAMEWORK)),
            source_of(os.path.join(MISSION_RUNNER_DIR, self.FRAMEWORK)),
            "the two copies have diverged again; a change that lands in one "
            "and not the other is its own bug")

    def test_the_update_context_carries_the_effects_and_the_settings(self):
        framework = collapsed(
            source_of(os.path.join(SAXRAT_DIR, self.FRAMEWORK)))
        self.assertIn(
            "previousStepsEffects : List (List "
            "Common.EffectOnWindow.EffectOnWindowStruct)", framework)
        self.assertIn("botSettings : botSettings", framework)

    def test_a_missing_location_panel_icon_waits_rather_than_crying_stuck(self):
        """The other half of the divergence, and general for the same reason:
        the icon is missing while the client is still drawing its UI, and a
        watcher that cries wolf on every dock cycle is one you stop reading."""
        framework = collapsed(
            source_of(os.path.join(SAXRAT_DIR, self.FRAMEWORK)))
        self.assertIn(
            "I do not see the icon for the location info panel yet -- wait "
            "for the client to draw it.", framework)
        self.assertNotIn(
            "I do not see the icon for the location info panel.", framework)


if __name__ == "__main__":
    unittest.main()
