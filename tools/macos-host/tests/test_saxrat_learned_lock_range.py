"""Tests for saxrat's lock range, which the client teaches it rather than a
setting asserting.

`targeting-range` decides whether saxrat locks a rat or flies at it, and until
this port saxrat carried `targetingRangeMeters = 66000` and never revised it.
The mission runner treats the same number as a starting guess and clamps it into
`[lockProvenAtMeters, lockRefusedAtMeters)` -- the greatest distance at which the
client accepted a lock, and the smallest at which it provably refused one. That
machinery was entirely absent here.

**The row-identity discipline is the part these cases exist for.** Attribution
is the whole safety of the rule: the overview re-sorts and virtualises, so a
screen position identifies a *row* and not an *object*, and matching a lock
outcome to the wrong object teaches a wrong range that is then sticky for the
session. The rule keys on EVE's own `itemID`, falls back to the row's name only
when no other row shares it, and yields **no evidence at all** from a pocket of
same-named rats. saxrat ratting in an anomaly is close to the worst case for
that -- an anomaly is a pocket of identically named rats by construction -- so
the "no evidence" branch is the common one here and the cases below pin it
directly rather than incidentally.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, for the reason CLAUDE.md's "How a change is verified here"
gives: a Python restatement of a rule tests the restatement. The overview rows
they are asked about come from the **real** `EveOnline.ParseUserInterface`, so
a hand-written record cannot drift from what the parser would have produced --
which is also what makes these cases evidence that saxrat's diverged copy of
that parser exposes the fields the identity rule needs.

The wiring and the placement -- which are not expressions and cannot be
evaluated -- are read out of the source through a whitespace-collapsing reader,
so an `elm-format` pass cannot break them.

Confirmed by mutation, thirteen of them, each failing a named case: the
same-name exclusion weakened to "at least one" (the mutation that matters most
here, and the one an anomaly meets on every reading), the item id ignored so
the name is the only handle, the empty-target-bar condition dropped, the verdict
count reached one reading early, the refusal interval closed rather than
half-open, a refusal allowed to override a lock that completed, the wait counter
pinned at a constant, the rendered-row filter dropped from the click
attribution, a ship that could not have locked treated as one that could, the
lock branch reading the raw setting again, the status line dropping the clause,
a moved bound no longer named in the decision log, and the proven bound written
back from memory rather than from the rule.

One of those survived the first time and the hole was real. The rendered-row
filter on the *click* is redundant with the one on the verdict for every
fixture where a hidden row is simply hidden -- both end in no attempt -- so
nothing caught its removal. What it is not redundant for is the case it exists
for: a stale row and the row now drawn where it used to be report the *same*
rectangle, and dropping the filter attributes the client's answer to whichever
comes first in the tree.
`test_a_recycled_region_is_resolved_to_the_row_being_drawn` builds exactly that.

Nothing here reads a live game client or a running bot. Two cases read the
recorded saxrat runs in `~/eve-bot-logs`, and only read them; they skip with a
stated reason on a machine that has none, which is the answer an absent piece of
*evidence* gets rather than the one an absent toolchain does.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, label, node, ship_ui,
    source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The run the issue quotes: the mission runner's run 36 read
# `Lock range: 59000 m (setting 37000, proven 59000, refused 67000)`, so the
# client corrected a configured value that was 22 km too low, in flight, from
# evidence it volunteered.
RUN_36 = {"setting": 37000, "proven": 59000, "refused": 67000, "answer": 59000}

# Row geometry. The rows are 20px apart starting at y=20 and 500 wide, so a
# click at the middle of row N lands inside that row's region and no other.
ROW_HEIGHT = 16
ROW_PITCH = 20
ROW_TOP = 20


def row_center(index):
    return (250, ROW_TOP + index * ROW_PITCH + ROW_HEIGHT // 2)


def overview_rows(rows, hidden=(), stacked=False):
    """An overview window whose rows carry item ids and lock indicators.

    `test_saxrat_ported_guards.overview` cannot express either, and both are
    exactly what the identity rule turns on -- so this builds the rows itself
    while reusing that file's node helpers.

    Each row is `(distance, name, item_id, targeted)`. `item_id` of `None`
    leaves the `itemID` entry off the node entirely, which is the case the name
    fallback exists for; `targeted` adds the `targetedByMeIndicator` under a
    `SpaceObjectIcon`, which is how the parser reads `commonIndications`.

    Rows whose index is in `hidden` carry `_display: False`. The overview
    virtualises, so such a row keeps a plausible region belonging to whatever
    was recycled into its place -- which is why nothing may be attributed to
    one, and why a fixture that cannot express one leaves that filter untested.

    `stacked` puts every row at the *same* region, which is that recycling
    written down: a hidden row and the row now drawn where it used to be report
    the same rectangle, and only `_display` tells them apart.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name, item_id, targeted) in enumerate(rows):
        y = ROW_TOP if stacked else ROW_TOP + index * ROW_PITCH
        entries_of_interest = {"_name": "overviewEntry"}
        if item_id is not None:
            entries_of_interest["itemID"] = item_id
        if index in hidden:
            entries_of_interest["_display"] = False

        icon_children = []
        if targeted:
            icon_children.append(
                node("Sprite", {"_name": "targetedByMeIndicator"}))

        entries.append(node("OverviewScrollEntry", entries_of_interest, [
            label(distance, (10, y, 50, ROW_HEIGHT)),
            label(name, (110, y, 150, ROW_HEIGHT)),
            label(name, (310, y, 150, ROW_HEIGHT)),
            node("SpaceObjectIcon", {}, icon_children,
                 region=(2, y, 12, ROW_HEIGHT)),
        ], region=(0, y, 500, ROW_HEIGHT)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def flying(maneuver=None):
    """A ship UI, optionally reporting a manoeuvre.

    `ship_ui` cannot express one, so the indication container is appended to
    what it builds rather than a second copy of it being written here. The
    parser reads the manoeuvre out of that container's display texts, so
    "Warp" is the client's own word rather than a code.
    """
    ui = ship_ui(100, 100, 4)
    if maneuver is not None:
        ui["children"].append(
            node("IndicationContainer", {"_name": "indicationContainer"},
                 [label(maneuver, (0, 60, 100, 16))], region=(0, 60, 100, 16)))
    return ui


class LockRangeRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus the bindings every case here needs.

    The helpers are Elm rather than Python string templates wherever they can
    be: `step` in particular folds the rule's own output back into its own
    input, which is the thing a session does and the thing a Python
    reconstruction of it would get to define for itself.
    """

    HELPERS = [
        "entriesOf = \\parsed -> parsed"
        " |> Maybe.map (.overviewWindows >> List.concatMap .entries)"
        " |> Maybe.withDefault []",
        "shipUIOf = \\parsed -> parsed |> Maybe.andThen .shipUI",
        # One reading, as the rule takes it, from a really parsed one.
        "lockReading = \\parsed targets effects ->"
        " { entries = entriesOf parsed, shipUI = shipUIOf parsed"
        " , targetsCount = targets, lastStepEffects = effects }",
        # The lock chord: Ctrl held over a plain left click.
        "lockClickAt = \\x y ->"
        " [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
        " , EffectOnWindow.MouseMoveTo { x = x, y = y }"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]",
        # The rule's own answer folded back into its own input, so a case can
        # run a session rather than one reading.
        "step = \\reading state ->"
        " let learned = updateLockRangeLearning reading state in"
        " { fromSetting = state.fromSetting"
        " , statedMeters = state.statedMeters"
        " , provenAtMeters = learned.provenAtMeters"
        " , refusedAtMeters = learned.refusedAtMeters"
        " , attempt = learned.attempt }",
        "changeOf = \\reading state ->"
        " (updateLockRangeLearning reading state).change",
        "noEvidence = { fromSetting = 66000, statedMeters = Nothing"
        " , provenAtMeters = Nothing"
        " , refusedAtMeters = Nothing, attempt = Nothing }",
    ]

    @staticmethod
    def entries_binding(name, rows):
        """`name` bound to the entries of one overview window, as parsed."""
        return SaxratRepl.reading_binding(name + "Reading",
                                          [overview_rows(rows)]) \
            + "\n%s = %sReading |> Maybe.map (.overviewWindows >>" \
              " List.concatMap .entries) |> Maybe.withDefault []" % (name, name)

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class ParsedRowsCarryWhatTheRuleNeedsTest(unittest.TestCase):
    """saxrat's diverged parser, asked directly for the fields this turns on.

    The two apps vendor *diverged* copies of `EveOnline/ParseUserInterface.elm`,
    so whether saxrat's copy exposes `objectItemID`, the lock indicators and a
    row region a click can be resolved against is a question about this app
    rather than about the shared code. It is asked here first, because every
    case below would otherwise pass or fail for reasons that have nothing to do
    with the rule.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_parser_gives_back_ids_names_regions_and_indicators(self):
        answers = self.repl.evaluate(
            ["List.length rows == 3",
             "(rows |> List.map .objectItemID) =="
             " [ Just \"111\", Nothing, Just \"333\" ]",
             "(rows |> List.map .objectName) =="
             " [ Just \"Centior Monster\", Just \"Centii Savage\""
             " , Just \"Centior Monster\" ]",
             "(rows |> List.map (.objectDistanceInMeters >>"
             " Result.withDefault -1)) == [ 5000, 6000, 7000 ]",
             "(rows |> List.map (.commonIndications >> .targetedByMe)) =="
             " [ False, False, True ]",
             # The region a click is resolved against: each row's own, distinct
             # from its neighbours'.
             "(rows |> List.map (.uiNode >> .totalDisplayRegion >> .y)) =="
             " [ %d, %d, %d ]" % (ROW_TOP, ROW_TOP + ROW_PITCH,
                                  ROW_TOP + 2 * ROW_PITCH),
             "(rows |> List.map (.uiNode >> .totalDisplayRegion >> .height)) =="
             " [ %d, %d, %d ]" % (ROW_HEIGHT, ROW_HEIGHT, ROW_HEIGHT)],
            definitions=[LockRangeRepl.entries_binding("rows", [
                ("5,000 m", "Centior Monster", "111", False),
                ("6,000 m", "Centii Savage", None, False),
                ("7,000 m", "Centior Monster", "333", True)])])
        self.assertEqual(
            answers, [True] * 7,
            "saxrat's copy of ParseUserInterface does not give the rule the "
            "fields it keys on, so nothing below would mean anything")


class LockRangeThresholdTest(unittest.TestCase):
    """The setting clamped into what the client has actually granted."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def threshold(self, setting, proven, refused):
        return ("lockRangeThresholdInMeters { fromSetting = %d"
                ", statedMeters = Nothing"
                ", provenAtMeters = %s, refusedAtMeters = %s"
                ", attempt = Nothing }"
                % (setting,
                   "Nothing" if proven is None else "Just %d" % proven,
                   "Nothing" if refused is None else "Just %d" % refused))

    def test_with_no_evidence_the_setting_stands_exactly(self):
        """`Nothing` in both directions is "nobody has asked", not "refused at
        0" -- so a session that learns nothing behaves as it always did."""
        answers = self.repl.evaluate([
            "%s == %d" % (self.threshold(setting, None, None), setting)
            for setting in (66000, 37000, 0, 250000)])
        self.assertEqual(
            answers, [True] * 4,
            "the setting no longer stands unchanged where there is no evidence")

    def test_a_refusal_lowers_the_setting_and_the_interval_is_half_open(self):
        """`lockRefusedAtMeters` is a distance a lock *failed* at, so the
        threshold has to sit strictly below it -- locking at exactly that
        distance is the thing the client has already declined."""
        answers = self.repl.evaluate([
            "%s == 59999" % self.threshold(66000, None, 60000),
            "%s == 66000" % self.threshold(66000, None, 70000),
            "%s == 66000" % self.threshold(66000, None, 66001),
            "%s == 65999" % self.threshold(66000, None, 66000)])
        self.assertEqual(
            answers, [True] * 4,
            "a refusal no longer lowers the threshold strictly below itself, "
            "or a refusal beyond the setting moved a setting it says nothing "
            "about")

    def test_a_proven_lock_raises_the_setting(self):
        """Run 36's own correction: a configured 37000 against a lock the
        client accepted at 59000. Nobody knew that number before the ship
        tried, which is the argument for learning it rather than tuning it."""
        answers = self.repl.evaluate([
            "%s == %d" % (self.threshold(RUN_36["setting"], RUN_36["proven"],
                                         RUN_36["refused"]),
                          RUN_36["answer"]),
            # A proven distance below the setting is no reason to lower it.
            "%s == 66000" % self.threshold(66000, 20000, None)])
        self.assertEqual(
            answers, [True] * 2,
            "a lock the client accepted no longer raises the threshold, or a "
            "short proven lock lowered a setting it does not contradict")

    def test_where_the_two_bounds_contradict_each_other_proven_wins(self):
        """Possible after a refit, since the bounds are not reset mid-session.

        A completed lock is unambiguous -- nothing but the client accepting
        makes a row read targeted -- where a refusal is an inference from
        several conditions holding at once, so the unambiguous evidence is the
        one that survives the disagreement.
        """
        answers = self.repl.evaluate([
            "%s == 60000" % self.threshold(66000, 60000, 40000),
            "%s == 60000" % self.threshold(30000, 60000, 40000)])
        self.assertEqual(
            answers, [True] * 2,
            "a refusal overrode a lock that actually completed")

    def test_the_lock_branch_asks_the_rule_rather_than_the_setting(self):
        """The whole point of the port, and the one line that could revert it
        while everything else still compiled and every bound still moved."""
        branch = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "lockTargetFromOverviewEntry"))
        self.assertIn(
            "targetingRange = lockRangeThresholdInMeters "
            "(lockRangeStateFrom context)", branch,
            "the lock/approach decision reads the raw setting again, so the "
            "bounds move and nothing acts on them")
        self.assertNotIn(
            "context.eventContext.botSettings.targetingRangeMeters", branch,
            "the branch still reads the setting directly somewhere")


class RowIdentityTest(unittest.TestCase):
    """Which row a lock outcome may be attributed to -- and, mostly, none.

    This is the part that must not be simplified. A screen position identifies
    a row; an `itemID` identifies an object; a name identifies an object only
    where no other row shares it. Anything looser teaches a wrong range from a
    pocket of identical rats, which is what an anomaly is.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_item_id_is_used_where_the_row_carries_one(self):
        """EVE's own id, which survives the overview re-sorting under it."""
        answers = self.repl.evaluate(
            ["(rows |> List.map (overviewEntryLockHandle rows)) =="
             " [ Just \"id:111\", Just \"id:222\" ]"],
            definitions=[LockRangeRepl.entries_binding("rows", [
                ("5,000 m", "Centior Monster", "111", False),
                ("6,000 m", "Centior Monster", "222", False)])])
        self.assertTrue(
            answers[0],
            "two rows sharing a name but carrying distinct item ids must "
            "still be told apart -- the id is what identifies the object")

    def test_a_unique_name_is_a_handle_and_a_shared_one_is_not(self):
        """The fallback, and the case it refuses.

        Three of five rats here are `Centior Monster` with no id: none of the
        three may produce a handle, because one of five identical rats says
        nothing about which one the client answered. The two unique names do.
        """
        answers = self.repl.evaluate(
            ["(rows |> List.map (overviewEntryLockHandle rows)) =="
             " [ Nothing, Just \"name:Centii Savage\", Nothing"
             " , Just \"name:R.S. Officer\", Nothing ]"],
            definitions=[LockRangeRepl.entries_binding("rows", [
                ("5,000 m", "Centior Monster", None, False),
                ("6,000 m", "Centii Savage", None, False),
                ("7,000 m", "Centior Monster", None, False),
                ("8,000 m", "R.S. Officer", None, False),
                ("9,000 m", "Centior Monster", None, False)])])
        self.assertTrue(
            answers[0],
            "the same-name exclusion has been weakened -- a row that cannot be "
            "told apart from another produced a handle anyway, which is how a "
            "lock outcome gets attributed to the wrong object")

    def test_a_second_row_taking_the_name_withdraws_the_handle(self):
        """The handle is a property of the *reading*, not of the row.

        A name that was unique when the attempt started and is shared by the
        time the verdict is due stops resolving, and the attempt is dropped
        rather than judged. That is the correct direction: a rat that warped in
        is exactly the ambiguity this rule exists to refuse.
        """
        answers = self.repl.evaluate(
            ["(alone |> List.map (overviewEntryLockHandle alone)) =="
             " [ Just \"name:Centior Monster\" ]",
             "(joined |> List.map (overviewEntryLockHandle joined)) =="
             " [ Nothing, Nothing ]"],
            definitions=[
                LockRangeRepl.entries_binding("alone", [
                    ("5,000 m", "Centior Monster", None, False)]),
                LockRangeRepl.entries_binding("joined", [
                    ("5,000 m", "Centior Monster", None, False),
                    ("9,000 m", "Centior Monster", None, False)])])
        self.assertEqual(answers, [True] * 2)

    def test_the_identity_rule_is_the_mission_runners_byte_for_byte(self):
        """The two apps' copies of the rule this port exists to carry across.

        The doc comments differ -- saxrat's says why the "no evidence" branch is
        the common case here -- but the code may not, and a divergence in it is
        a divergence in what a lock outcome is allowed to be attributed to.
        """
        for name in ("overviewEntryLockHandle", "locationIsInDisplayRegion"):
            self.assertEqual(
                collapsed(body_of(source_of(SAXRAT_BOT_ELM), name)),
                collapsed(body_of(source_of(MISSION_RUNNER_BOT_ELM), name)),
                "%s has diverged from the mission runner's; the identity rule "
                "is the safety of this feature and is not app-specific" % name)


class LockClickAttributionTest(unittest.TestCase):
    """Which dispatched effects count as a lock, and where they went."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_only_the_lock_chord_yields_a_location(self):
        """saxrat presses Ctrl in three places and only one is a lock.

        `ctrlShiftClickUiElement` is the unlock and holds Shift as well; the
        loot window's Ctrl+W carries no mouse effect at all, so there is no
        `MouseMoveTo` to take. The approach chord presses `vkey_E` and no Ctrl.
        Each of the three must answer `Nothing`, and the mission runner's own
        argument ("the only place that presses Ctrl without Shift") is *not*
        true here, which is why both conditions are checked.
        """
        unlock = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
                  ", EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.MouseMoveTo { x = 300, y = 40 }"
                  ", EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
                  ", EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]")
        close_loot = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
                      ", EffectOnWindow.KeyDown EffectOnWindow.vkey_W"
                      ", EffectOnWindow.KeyUp EffectOnWindow.vkey_W"
                      ", EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]")
        approach = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_E"
                    ", EffectOnWindow.MouseMoveTo { x = 300, y = 40 }"
                    ", EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
                    ", EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft"
                    ", EffectOnWindow.KeyUp EffectOnWindow.vkey_E ]")
        answers = self.repl.evaluate(
            ["lockClickLocationsFromStepEffects (lockClickAt 300 40)"
             " == [ { x = 300, y = 40 } ]",
             "lockClickLocationsFromStepEffects %s == []" % unlock,
             "lockClickLocationsFromStepEffects %s == []" % close_loot,
             "lockClickLocationsFromStepEffects %s == []" % approach,
             "lockClickLocationsFromStepEffects [] == []"],
            definitions=self.repl.with_helpers([]))
        self.assertEqual(
            answers, [True] * 5,
            "a gesture that is not a lock was read as one, or the lock chord "
            "stopped being recognised")

    def test_a_click_belongs_to_the_row_whose_region_contains_it(self):
        """Half-open on both axes, so two rows that touch cannot both claim a
        point on their shared edge."""
        region = "{ x = 0, y = 20, width = 500, height = 16 }"
        answers = self.repl.evaluate([
            "locationIsInDisplayRegion { x = 250, y = 28 } %s" % region,
            "locationIsInDisplayRegion { x = 0, y = 20 } %s" % region,
            "locationIsInDisplayRegion { x = 500, y = 28 } %s == False" % region,
            "locationIsInDisplayRegion { x = 250, y = 36 } %s == False" % region,
            "locationIsInDisplayRegion { x = 250, y = 19 } %s == False" % region])
        self.assertEqual(answers, [True] * 5)


class LearningASessionTest(unittest.TestCase):
    """The rule folded over readings, which is what a session is.

    Every case here runs `updateLockRangeLearning` for real and feeds its own
    answer back in, so what is checked is the sequence a run would produce
    rather than one reading in isolation.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    # One rat with an id, one without, and a pocket of identical ones.
    IDENTIFIED = [("60,000 m", "Centior Monster", "111", False)]
    IDENTIFIED_TARGETED = [("60,000 m", "Centior Monster", "111", True)]
    ANONYMOUS_POCKET = [("60,000 m", "Centior Monster", None, False),
                        ("61,000 m", "Centior Monster", None, False),
                        ("62,000 m", "Centior Monster", None, False)]
    # The stale row first, so parser order alone would pick the wrong one.
    RECYCLED = [("20,000 m", "Centior Monster", "111", False),
                ("60,000 m", "Centii Savage", "222", False)]

    def definitions(self):
        """Whole readings, each carrying an overview *and* a ship UI.

        The ship UI is not decoration: `shipCannotLock` is one of the rule's
        own judgements, so a fixture built without one would make every case
        below pass through the "the ship could not have locked anything"
        branch and assert nothing about range at all.
        """
        return self.repl.with_helpers([
            SaxratRepl.reading_binding(
                "waiting", [overview_rows(self.IDENTIFIED), flying()]),
            SaxratRepl.reading_binding(
                "locked", [overview_rows(self.IDENTIFIED_TARGETED), flying()]),
            SaxratRepl.reading_binding(
                "pocket", [overview_rows(self.ANONYMOUS_POCKET), flying()]),
            SaxratRepl.reading_binding("gone", [overview_rows([]), flying()]),
            SaxratRepl.reading_binding(
                "hidden",
                [overview_rows(self.IDENTIFIED, hidden=(0,)), flying()]),
            # A stale row and the row now drawn where it used to be, reporting
            # the same rectangle -- the overview's recycling written down.
            SaxratRepl.reading_binding(
                "recycled",
                [overview_rows(self.RECYCLED, hidden=(0,), stacked=True),
                 flying()]),
            SaxratRepl.reading_binding(
                "warping",
                [overview_rows(self.IDENTIFIED), flying(maneuver="Warp")]),
            # No ship UI at all: the docked case.
            SaxratRepl.reading_binding(
                "docked", [overview_rows(self.IDENTIFIED)]),
        ])

    def click(self, parsed, row=0, targets=0):
        x, y = row_center(row)
        return "lockReading %s %d (lockClickAt %d %d)" % (parsed, targets, x, y)

    def idle(self, parsed, targets=0):
        return "lockReading %s %d []" % (parsed, targets)

    def fold(self, readings, start="noEvidence"):
        folded = start
        for reading in readings:
            folded = "step (%s) (%s)" % (reading, folded)
        return folded

    def test_a_pocket_of_identical_rats_teaches_nothing_at_all(self):
        """The branch that must be preserved exactly, and the common one here.

        Three identically named rats with no item ids: the click lands on a real
        rendered row at a real distance, the lock never completes, the target
        bar is empty at both ends and the readings run well past the verdict
        count -- every condition a refusal needs *except* being able to say
        which object the client was answering about. No attempt is ever opened
        and neither bound moves.

        Loosening this is what makes the feature fire often and occasionally
        learn a wrong range, which is worse than a feature that rarely fires:
        the wrong bound is sticky for the whole session.
        """
        session = self.fold([self.click("pocket")]
                            + [self.idle("pocket")] * 20)
        answers = self.repl.evaluate(
            ["(%s).attempt == Nothing" % session,
             "(%s).provenAtMeters == Nothing" % session,
             "(%s).refusedAtMeters == Nothing" % session,
             "changeOf (%s) (%s) == Nothing"
             % (self.idle("pocket"), session)],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 4,
            "a pocket of same-named rats produced evidence -- the row-identity "
            "rule has been loosened and the bot can now learn a range from a "
            "lock it cannot attribute")

    def test_a_lock_that_lands_teaches_the_proven_distance(self):
        """A row that reads `targetedByMe` is the client having accepted, and
        nothing else makes a row read that way."""
        session = self.fold([self.click("waiting"), self.idle("locked")])
        answers = self.repl.evaluate(
            ["(%s).provenAtMeters == Just 60000" % session,
             # A completed lock ends the attempt; nothing is left waiting.
             "(%s).attempt == Nothing" % session,
             "(%s).refusedAtMeters == Nothing" % session,
             "changeOf (%s) (%s) /= Nothing"
             % (self.idle("locked"),
                self.fold([self.click("waiting")]))],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 4,
            "a lock the client accepted no longer moves the proven bound, or "
            "moves it without saying so")

    def test_a_refusal_needs_the_full_count_of_readings(self):
        """A merely slow lock is not a refused one. A big ship locking a small
        one takes seconds, and calling that a refusal teaches a range that is
        too short and sends the bot flying at rats it could have shot."""
        [count] = self.repl.evaluate(
            ["lockAttemptReadingsBeforeVerdict == 8"])
        self.assertTrue(count, "the verdict count moved off its value")

        short = self.fold([self.click("waiting")] + [self.idle("waiting")] * 7)
        full = self.fold([self.click("waiting")] + [self.idle("waiting")] * 8)
        answers = self.repl.evaluate(
            ["(%s).refusedAtMeters == Nothing" % short,
             "(%s).refusedAtMeters == Just 60000" % full],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "the refusal fires early, or no longer fires at all -- one reading "
            "either side of the verdict count must differ")

    def test_a_target_bar_that_was_not_empty_proves_nothing_about_range(self):
        """What separates "too far" from "no free slot".

        An empty target bar is the only thing a reading can say that *proves* a
        slot was free -- the client's own maximum is not in the reading at all,
        and `max-target-count` is this bot's ceiling rather than the client's.
        Without this the bound ratchets down every time the ship simply fills
        up, which for a bot that locks four rats and holds them is most of the
        time.
        """
        at_the_start = self.fold(
            [self.click("waiting", targets=1)]
            + [self.idle("waiting")] * 8)
        at_the_end = self.fold(
            [self.click("waiting")]
            + [self.idle("waiting")] * 7 + [self.idle("waiting", targets=1)])
        answers = self.repl.evaluate(
            ["(%s).refusedAtMeters == Nothing" % at_the_start,
             "(%s).refusedAtMeters == Nothing" % at_the_end],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "a lock that never landed while the ship already held a target was "
            "read as evidence about range rather than about capacity")

    def test_a_row_that_leaves_the_overview_ends_the_attempt_unjudged(self):
        """It may have died, or scrolled out of view, or the overview may have
        re-sorted -- none of which says anything about range."""
        session = self.fold([self.click("waiting")]
                            + [self.idle("waiting")] * 4
                            + [self.idle("gone")])
        answers = self.repl.evaluate(
            ["(%s).attempt == Nothing" % session,
             "(%s).refusedAtMeters == Nothing" % session,
             "(%s).provenAtMeters == Nothing" % session],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 3,
            "a row that disappeared mid-attempt was judged anyway")

    def test_a_row_that_is_not_rendered_is_never_attributed_anything(self):
        """The overview virtualises, and a hidden row is the whole reason the
        attribution has to be careful at all: it keeps a plausible region
        pointing at a row that now belongs to something else. So a click
        resolved against one is not a click on that object, and an attempt
        whose row stops being rendered is dropped rather than judged.
        """
        clicked_hidden = self.fold([self.click("hidden")]
                                   + [self.idle("hidden")] * 8)
        went_hidden = self.fold(
            [self.click("waiting")] + [self.idle("waiting")] * 7
            + [self.idle("hidden")])
        # The case the two filters are not redundant in, and the one a
        # surviving mutation found: the row is not rendered on the reading the
        # click is resolved against and *is* rendered by the time a verdict
        # would be due. Attributing the click to it there is attributing it to
        # whatever the client had recycled into that row's place, and the
        # verdict then arrives looking exactly like an honest one.
        hidden_then_shown = self.fold([self.click("hidden")]
                                      + [self.idle("waiting")] * 8)
        answers = self.repl.evaluate(
            ["(%s).attempt == Nothing" % clicked_hidden,
             "(%s).refusedAtMeters == Nothing" % clicked_hidden,
             "(%s).attempt == Nothing" % went_hidden,
             "(%s).refusedAtMeters == Nothing" % went_hidden,
             "(%s).attempt == Nothing" % hidden_then_shown,
             "(%s).refusedAtMeters == Nothing" % hidden_then_shown],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 6,
            "a row the client was not rendering was treated as the object the "
            "click hit, which is how a lock outcome lands on whatever was "
            "recycled into that row's place")

    def test_a_recycled_region_is_resolved_to_the_row_being_drawn(self):
        """Two rows reporting one rectangle, which is what recycling looks like.

        The stale row comes first in the tree, so anything that resolves a
        click by region alone picks it -- and then attributes the client's
        answer to an object 40 km from where the click actually landed. The
        filter is what makes the *right* row win rather than merely making
        nothing win: the attempt here carries the drawn row's id and distance,
        and reaches a verdict about it.
        """
        session = self.fold([self.click("recycled")]
                            + [self.idle("recycled")] * 8)
        answers = self.repl.evaluate(
            ["((%s).attempt |> Maybe.map .handle) == Just \"id:222\""
             % self.fold([self.click("recycled")]),
             "(%s).refusedAtMeters == Just 60000" % session],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "a click landing where a stale row still reports a rectangle was "
            "attributed to that row rather than to the one the client was "
            "actually drawing there")

    def test_a_ship_that_could_not_have_locked_anything_is_not_evidence(self):
        """Nothing is lockable in warp or from inside a station.

        The bot cannot *start* an attempt in either state, but it can be
        halfway through one when the ship warps out of a pocket it is losing,
        and a lock nobody could have granted must not read as one the ship was
        too far away for. The control is the same session on a ship that stayed
        put, which does reach a verdict.
        """
        put_up_with_it = [self.click("waiting")] + [self.idle("waiting")] * 8
        answers = self.repl.evaluate(
            ["(%s).refusedAtMeters == Just 60000" % self.fold(put_up_with_it),
             # The last reading of the same session, warping.
             "(%s).refusedAtMeters == Nothing"
             % self.fold(put_up_with_it[:-1] + [self.idle("warping")]),
             "(%s).attempt == Nothing"
             % self.fold(put_up_with_it[:-1] + [self.idle("warping")]),
             # And docked, which is the reading with no ship UI at all.
             "(%s).refusedAtMeters == Nothing"
             % self.fold(put_up_with_it[:-1] + [self.idle("docked")]),
             "(%s).attempt == Nothing"
             % self.fold(put_up_with_it[:-1] + [self.idle("docked")])],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 5,
            "a lock the client could not have granted -- the ship in warp, or "
            "docked -- was judged as one the ship was too far away for")

    def test_the_bounds_move_one_way_only_and_say_so_once(self):
        """Monotone in both directions, which is what makes oscillation
        impossible and what makes one line per change need no "already
        reported" flag: a repeated verdict moves nothing and says nothing."""
        # Both bounds already at least as tight as this rat at 60,000 m can
        # make them: a lock accepted at 60,000 m is not further than the 60,000
        # already proven, and a refusal at 60,000 m is not tighter than the
        # 50,000 already refused.
        learned = ("{ fromSetting = 66000, statedMeters = Nothing"
                   ", provenAtMeters = Just 60000"
                   ", refusedAtMeters = Just 50000, attempt = Nothing }")
        accepted = self.fold([self.click("waiting"), self.idle("locked")],
                             start=learned)
        refused = self.fold([self.click("waiting")]
                            + [self.idle("waiting")] * 8, start=learned)
        answers = self.repl.evaluate(
            ["(%s).provenAtMeters == Just 60000" % accepted,
             "changeOf (%s) (%s) == Nothing"
             % (self.idle("locked"),
                self.fold([self.click("waiting")], start=learned)),
             "(%s).refusedAtMeters == Just 50000" % refused,
             "changeOf (%s) (%s) == Nothing"
             % (self.idle("waiting"),
                self.fold([self.click("waiting")]
                          + [self.idle("waiting")] * 7, start=learned))],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 4,
            "a bound moved backwards, or a verdict that changed nothing "
            "announced itself anyway -- which is one log line per reading")

    def test_the_readings_waited_counter_advances_and_is_capped(self):
        """The mutation `test_ammo_silenced_bound` was written to catch: a
        counter pinned at a constant satisfies "it is mentioned".

        The reading the click is seen on is itself the first reading waited, so
        the count runs one ahead of the number of readings since. It is then
        held at the bound rather than allowed to run on, because the number is
        shown to an operator and one that climbs forever reads as a fault.
        """
        def waited(readings):
            return ("((%s).attempt |> Maybe.map .readingsWaited)"
                    % self.fold([self.click("waiting")]
                                + [self.idle("waiting")] * readings))

        answers = self.repl.evaluate(
            ["%s == Just 1" % waited(0),
             "%s == Just 2" % waited(1),
             "%s == Just 6" % waited(5),
             "%s == Just 8" % waited(7),
             "%s == Just 8" % waited(30)],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 5,
            "the wait counter does not advance one reading at a time, or is "
            "not held at the verdict count once it is spent")

    def test_clicking_another_row_abandons_the_old_attempt(self):
        """Nobody is waiting on it, so it is dropped rather than judged --
        which also means a bot switching targets cannot accumulate a verdict
        out of two different objects' readings."""
        two_rows = [("60,000 m", "Centior Monster", "111", False),
                    ("70,000 m", "Centii Savage", "222", False)]
        session = self.fold(
            ["lockReading pair 0 (lockClickAt %d %d)" % row_center(0)]
            + ["lockReading pair 0 []"] * 4
            + ["lockReading pair 0 (lockClickAt %d %d)" % row_center(1)]
            + ["lockReading pair 0 []"] * 7)
        answers = self.repl.evaluate(
            ["((%s).attempt |> Maybe.map .handle) == Just \"id:222\"" % session,
             "((%s).attempt |> Maybe.map .distanceInMeters) == Just 70000"
             % session,
             # Seven readings after the second click is one short of a verdict,
             # so the first attempt's readings did not carry over.
             "(%s).refusedAtMeters == Nothing" % session],
            definitions=self.repl.with_helpers(
                [SaxratRepl.reading_binding(
                    "pair", [overview_rows(two_rows), flying()])]))
        self.assertEqual(
            answers, [True] * 3,
            "an attempt on one row was continued as an attempt on another, so "
            "readings spent waiting on one object counted towards a verdict "
            "about a different one")


class StatusAndWiringTest(unittest.TestCase):
    """That the numbers reach an operator, and that the rule reaches the bot."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_clause_names_the_threshold_the_setting_and_both_bounds(self):
        """All four, because they answer different questions: which number the
        bot is acting on, which one an operator configured, and what the client
        has said. A clause carrying only the first cannot distinguish "the
        setting is right" from "the setting was overruled"."""
        [nothing_known, run_36] = self.repl.strings([
            "describeLockRange { fromSetting = 66000, statedMeters = Nothing"
            ", provenAtMeters = Nothing"
            ", refusedAtMeters = Nothing, attempt = Nothing }",
            "describeLockRange { fromSetting = %d, statedMeters = Nothing"
            ", provenAtMeters = Just %d"
            ", refusedAtMeters = Just %d, attempt = Nothing }"
            % (RUN_36["setting"], RUN_36["proven"], RUN_36["refused"])])
        self.assertEqual(
            nothing_known,
            "lock 66000m (set 66000 client - proven - refused - "
            "attempt none).")
        self.assertEqual(
            run_36,
            "lock 59000m (set 37000 client - proven 59000 refused 67000 "
            "attempt none).")

    def test_a_pending_attempt_is_reported_with_its_distance_and_age(self):
        """A bot clicking a lock it will never get shows up as an attempt
        sitting at the verdict count long before either bound has anything to
        say -- and, in an anomaly, an attempt reading `none` reading after
        reading is the identity rule declining to attribute, which is expected
        here rather than a fault."""
        [pending] = self.repl.strings([
            "describeLockRange { fromSetting = 66000, statedMeters = Nothing"
            ", provenAtMeters = Nothing"
            ", refusedAtMeters = Nothing, attempt = Just"
            " { handle = \"id:111\", distanceInMeters = 60000"
            ", targetsCount = 0, readingsWaited = 8 } }"])
        self.assertIn("attempt 60000m/8 readings", pending)

    def test_the_status_line_carries_the_clause(self):
        status = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "statusTextFromState"))
        self.assertIn(
            "describeLockRange (lockRangeStateFrom context)", status,
            "the status line no longer reports the lock range, so a number the "
            "bot adjusts for itself adjusts invisibly")

    def test_the_memory_update_writes_all_four_fields(self):
        """The rule runs in `updateMemoryForNewReadingFromGame` because that is
        the only place that can write memory and the one place that never sees
        the decision -- so a branch reading the click where it acts on it would
        see it once and behave exactly as before."""
        update = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "updateMemoryForNewReadingFromGame"))
        self.assertIn(
            "lockRangeLearning = updateLockRangeLearning "
            "(lockRangeReadingFrom context)", update,
            "the memory update no longer runs the rule")
        for field, source in [
                ("lockAttempt", "lockRangeLearning.attempt"),
                ("lockProvenAtMeters", "lockRangeLearning.provenAtMeters"),
                ("lockRefusedAtMeters", "lockRangeLearning.refusedAtMeters"),
                ("lockRangeLastChange", "lockRangeLearning.change")]:
            self.assertIn(
                "%s = %s" % (field, source), update,
                "%s is no longer written from the rule's own answer" % field)

    def test_a_bound_that_moves_says_so_at_the_root(self):
        """Announced at the root rather than in a branch: the bounds move in
        the memory update, which runs on every reading whatever the bot is
        doing, so the branch that learned it is not reliably the branch being
        evaluated. #102's shape, avoided by placement."""
        root = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "anomalyBotDecisionRoot"))
        self.assertIn(
            "|> List.filterMap identity |> List.foldr describeBranch", root,
            "the root no longer folds the memory update's own conclusions in")
        folded = root[:root.index("|> List.filterMap identity")]
        self.assertIn(
            "context.memory.lockRangeLastChange", folded,
            "a bound the bot moved for itself no longer names itself in the "
            "decision log")

    def test_the_rules_are_functions_of_records_rather_than_of_a_context(self):
        """Which is what makes every case above possible at all.

        A rule reachable only through a whole `BotDecisionContext` -- which
        carries a screenshot and a framework event context -- can be checked by
        reading it and in no other way. #106 records what that costs: the
        version of a rule it replaced "could not be executed, since it was
        reachable only through a whole BotDecisionContext, and that is exactly
        why the shipped version was checked by reading it".
        """
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        for signature in (
                "lockRangeThresholdInMeters : LockRangeState -> Int",
                "describeLockRange : LockRangeState -> String",
                "updateLockRangeLearning : LockRangeReading -> LockRangeState "
                "-> LockRangeLearning"):
            self.assertIn(
                signature, source,
                "%s takes a context again, so it can no longer be executed by "
                "a case" % signature.split(" :")[0])


class WhatTheRecordedSaxratRunsCanAndCannotSayTest(unittest.TestCase):
    """The three recorded saxrat runs, asked the two questions they bear on.

    Asserted as *relations* rather than as counts, so a corpus that grows
    cannot turn a true claim red.
    """

    @classmethod
    def setUpClass(cls):
        logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
                for number in (1, 2, 3)]
        logs = [path for path in logs if os.path.exists(path)]
        if not logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "can say about item ids cannot be consulted here")

        cls.wrecks_opened = 0
        cls.lock_range_clauses = 0
        opened = re.compile(r"Wrecks already opened: (\d+)")
        for path in logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = opened.search(line)
                    if match:
                        cls.wrecks_opened = max(cls.wrecks_opened,
                                                int(match.group(1)))
                    if "Lock range:" in line:
                        cls.lock_range_clauses += 1

    def test_overview_rows_on_this_client_do_carry_item_ids(self):
        """Indirect, and the only evidence the recordings hold.

        `lootedWreckIds` only grows through `Maybe.andThen .objectItemID` on an
        overview row, so a saxrat run whose `Wrecks already opened:` count ever
        left zero is a run in which the parser resolved a real `itemID` off a
        real row. That settles that the field reaches this client at all --
        which is the half of #121's open question that could be settled without
        flying anything.
        """
        self.assertGreater(
            self.wrecks_opened, 0,
            "no recorded saxrat run ever resolved an item id off an overview "
            "row, so nothing here says the field reaches this client")

    def test_the_recordings_cannot_say_whether_a_rat_carries_one(self):
        """And that is the other half, which only a run can answer.

        Every id the runs resolved came from a *wreck*, because that is the one
        consumer saxrat had. No recorded run carries a `Lock range:` clause --
        they predate it entirely -- so a rat's own row has never been asked,
        and this case exists so that "the corpus is silent" is a checked claim
        rather than a remembered one.
        """
        self.assertEqual(
            self.lock_range_clauses, 0,
            "a recorded saxrat run carries a lock-range clause after all, so "
            "the corpus can be asked what a rat's row resolves to and this "
            "file should be asking it")


if __name__ == "__main__":
    unittest.main()
