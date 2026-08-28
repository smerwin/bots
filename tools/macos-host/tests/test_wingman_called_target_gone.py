"""Tests for a called target that dies leaving the banner naming it.

#395, and it is #360 and #389 in a third variant. **The broadcast banner is a
last-broadcast display and never clears**, so when the commander's called target
dies the banner goes on naming it: `calledTargetIsLocked` answers `False`
because the thing is gone, `bringCalledTargetUnderFire` answered
`Just (lock it)`, and `lockCalledTarget` -- finding no overview row -- answered
`waitForProgressInGame`, a wait with no bound and no give-up. Because the arm
answered `Just`, the drones, the guns, the gate and the approach below it were
all unreachable for the rest of the session or until the FC called something
else. Live on 2026-08-28: three of four wingmen killed 37 rats each and stopped
together, 25 repeats each in a 400-line scrollback with `Weapons: nothing
locked`. Identical kill counts across the three is the tell -- they stopped at
the same moment, when the called target died.

Those live observations are #395's; there is no recorded corpus, no game log and
no client on the machine these cases run on, so **nothing here recomputes them**
and no case rests on them.

## Which of the issue's two shapes this is

The issue offers a bounded counter and a latch on the banner text, in that order,
and calls the latch the more general fix. What shipped is the **counter, with the
latch's identity half folded into it**: `BotMemory.calledTargetGone` carries the
called name beside the count, so the two clearing rules are one clause.

A pure latch on "this banner has been acted on" is the wrong shape for the
`Target` form and `fleetBroadcastFollowed` is why it looks right. That one bounds
a **one-shot** action -- the ESI route ask goes out once per banner and repeating
it is pure waste. A target call is a *standing* instruction: #360 already
established that the arm must answer `Nothing` while the target is locked and
`Just` again the moment it is not, because a lock can break and the call is still
live. A latch fired when the arm first acts would stop the bot re-locking a
target whose lock broke; a latch fired on "this call names nothing on the grid"
is the counter, one reading early. So the latch's *event* had to be the gone
verdict either way, and what the latch contributes is the name.

**What clears it**, since a latch nothing clears ignores the next call:
`calledTargetGoneAfterReading` answers `Nothing` on every reading that is not
"the banner names a target no overview row carries", which is all three of a row
coming back, a different target being called, and the banner going away. A
different call resets the count to one rather than inheriting the last call's,
which is the half a bare counter cannot do and the case
`test_a_different_call_starts_its_own_count` is what pins.

## The property, and it is not "it stops re-locking"

#360's fix has a property #395 asks to be carried: **once there is nothing more
to do about the call, the reading falls through.** That is what
`TheReadingFallsThroughTest` asserts, in the shape both predecessor branches
already use -- the real `actOnFleetBroadcast` over a real parsed reading,
required to answer `FELL THROUGH`, **with a control in the same call that must
still act**, so a rule answering `Nothing` for everything cannot pass.

`test_the_grace_is_bounded_by_the_real_memory_update` is the strongest of them:
it folds the shipped `updateMemoryForNewReadingFromGame` over a session of
identical readings and asks the shipped arm about the memory that fold produced,
so what is executed is the counter, the verdict and the arm together rather than
three rules asked separately.

## What is unverified, and these cases cannot close it

**Any of it running.** No wingman run has been flown since. What to watch on the
first one that meets a called target that dies: the status line's
`No row has named it for N of 3 readings` appearing and then
`GIVEN UP ON after N readings naming no row`, with ordinary decisions -- drones,
guns, the gate -- resuming underneath it on the same readings. A run that meets
one and never prints either clause means the counter is not being written, which
is the direction this fails silently in. The failure to watch for in the other
direction is the clause appearing on a call the bot could have acted on, which
would mean the row was there and `overviewRowsForPilot` did not match it.

**Whether a called target's row can vanish and return** is not established
either. `CalledNameNamesNoOverviewRow` is not the overview virtualising -- a
scrolled-out row is still in the tree and still answers
`CalledObjectIsNotAGate` -- so a live target reaches this state only by leaving
the overview's own range filter or through a reading that did not parse. The
bound is sized for the second; if the first turns out to be common, the tell is
the count climbing to 1 or 2 and resetting over and over while the bot goes on
locking the target normally.

The cases run the real `Bot.elm` through `elm repl`, and the readings they are
asked about go through the real `EveOnline.ParseUserInterface`. Nothing here
reads a live client, the recorded corpus, or a running bot.

## Confirmed by mutation

Eighteen, none of them surviving, each failing at least one named case:

| the mutation | what it breaks |
|---|---|
| **the give-up dropped, so the arm holds the reading again** -- #395 restored | the fall-through, 4 cases |
| **the count never cleared by a reading that is not the state** | `test_a_row_coming_back_clears_it`, 2 cases |
| **a different call inheriting the last call's count** -- the next call ignored | `test_a_different_call_starts_its_own_count`, 2 cases |
| the verdict's comparison weakened to `<=` | `test_the_give_up_fires_one_reading_past_the_bound`, 2 cases |
| the verdict's comparison moved one reading late | the boundary and the clause, 5 cases |
| the bound retuned to 40 | `test_the_bound_is_small_beside_the_bounds_on_a_click` |
| the bound retuned to 0, so one reading gives up | `test_one_reading_of_it_is_not_a_verdict`, 4 cases |
| the counter advancing on every reading carrying a call | `test_a_row_that_names_it_counts_nothing`, 2 cases |
| the counter advancing on a called gate that is merely not drawn | `test_a_gate_row_that_is_not_drawn_is_not_a_missing_name` |
| the counter advancing on a call on a fleetmate | `test_a_call_the_arm_never_reaches_spends_nothing` |
| the verdict answering for any name | `test_the_verdict_refuses_to_answer_for_another_name` |
| the memory update restating the arm's precondition | `test_the_arm_and_the_counter_read_one_rule` |
| the give-up asked after the lock rather than before | `test_the_give_up_is_asked_before_the_lock` |
| the status clause dropped from `describeCalledObject` | `test_the_clause_is_in_the_status_line`, 2 cases |
| the clause speaking about a different call | `test_the_clause_says_nothing_about_another_call` |
| the counter never advanced at all | `test_the_session_really_counted_what_that_case_thinks`, 3 cases |
| `overviewEntryForPilot` filtering on `_display`, which makes the unbounded wait reachable from a state nothing here bounds | `test_the_unbounded_wait_is_reachable_from_one_state_only` |
| the status line no longer printing the called-object clause | `test_the_status_line_calls_the_clause` |

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    label, node, reading_binding)
from test_wingman_called_gate import (  # noqa: E402
    GATE, RAT, drones_window, gate_row, overview, rat_row, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

#: The target the commander called in #395's own incident, and a second one, so
#: "a different call" is a call and not a placeholder.
DEAD = "Centus Black Ops Veteran"
OTHER = "Centus Dark Lord"
#: A fleetmate, for the guard that sits above this arm and must spend none of
#: its budget.
MATE = "Greta Gneiss"


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case.

    #58's reformatting broke three assertions written against exact
    indentation; every source-reading case here goes through this.
    """
    return " ".join(text.split())


def without_comments(text):
    """The same source with its `--` line comments dropped.

    `collapsed` would otherwise put a comment on the same line as the code it
    sits above, so every case asserting a branch's shape -- or a name's absence
    -- needs this first. The comments here name the very constructors those
    cases assert are not being re-derived.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def bot_source():
    with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
        return handle.read()


def declaration(name, source=None):
    """One top-level declaration, from its type annotation to the next gap."""
    source = bot_source() if source is None else source
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return rest[:rest.index("\n\n\n")]


def int_constant(name):
    """A constant read out of `Bot.elm`, so the cases below run against the
    shipped number rather than one restated here."""
    body = declaration(name)
    return int(body.split("\n%s =" % name)[1].split()[0])


def fleet_window(banner=None, members=()):
    """A `FleetWindow` carrying a broadcast banner and member rows.

    `fleetBroadcastBannerText` reads a descendant named `bannerLabel`;
    `fleetMemberNames` reads the display text of every descendant named
    `entryLabel`. Both are needed here because the fleet-member guard sits above
    this arm and the counter has to decline exactly the readings it declines.
    """
    children = []
    if banner is not None:
        children.append(
            label("Target %s" % banner, (10, 10, 300, 16), name="bannerLabel"))
    children.extend(
        node("FleetMember", {}, [
            label(member, (10, 100 + index * 20, 200, 16), name="entryLabel"),
        ], region=(0, 100 + index * 20, 300, 20))
        for index, member in enumerate(members))
    return node("FleetWindow", {}, children, region=(0, 0, 300, 400))


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    Every field of the context is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide an answer except the reading and the
    memory a case names -- `test_wingman_called_gate`'s arrangement, memory as an
    argument included, since most of the cases here are about what a spent
    budget does.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.DecisionPath",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "contextWith = \\memory -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # `FELL THROUGH` is a sentence no branch produces, so it reads as the
        # arm answering `Nothing` rather than as some decision this file failed
        # to anticipate.
        "describeArm = \\answer -> answer"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "FELL THROUGH"',
        "broadcastArm = \\memory -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " describeArm (actOnFleetBroadcast (contextWith memory p) s)))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "describeCalled = \\memory -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> describeCalledObject (contextWith memory p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # What the shipped rule makes of one reading, as the name it counts for
        # or `-` -- so a case sees which call the counter would advance on
        # rather than only that it advanced.
        "noRowFor = \\parsed -> parsed"
        " |> Maybe.andThen (calledTargetWithNoOverviewRow"
        "     defaultBotSettings.followFleetBroadcastFrom)"
        ' |> Maybe.withDefault "-"',
        # The pure counter folded over a session, printed as `name:count` or
        # `-`, so the clearing rules are run rather than asked one reading at a
        # time.
        "goneOver = \\names -> names"
        " |> List.foldl (\\n -> \\m -> calledTargetGoneAfterReading m"
        '     (if n == "-" then Nothing else Just n)) Nothing'
        " |> Maybe.map (\\g -> g.calledTarget"
        '     ++ ":" ++ String.fromInt g.readings)'
        ' |> Maybe.withDefault "-"',
        # `updateMemoryForNewReadingFromGame` folded over real readings, giving
        # back the memory itself so an arm can then be asked about it. `-1`
        # readings where any fixture never arrived, so a broken fixture cannot
        # read as a session that counted nothing.
        "memoryOver = \\readings ->"
        " if List.any ((==) Nothing) readings then"
        " { initBotMemory | calledTargetGone ="
        '     Just { calledTarget = "THE FIXTURE NEVER ARRIVED", readings = -1 } }'
        " else (readings |> List.filterMap identity |> List.foldl (\\r -> \\m ->"
        " updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = r"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = defaultBotSettings } m) initBotMemory)",
        "goneAfter = \\readings -> (memoryOver readings).calledTargetGone"
        " |> Maybe.map (\\g -> g.calledTarget"
        '     ++ ":" ++ String.fromInt g.readings)'
        ' |> Maybe.withDefault "-"',
        # A record built by hand, for the cases about the verdict's own
        # boundary rather than about how a session reaches it.
        "goneRecord = \\name -> \\readings ->"
        " Just { calledTarget = name, readings = readings }",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-called-target-gone-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


#: #395's own reading: the commander's called target is dead, so no overview row
#: names it, and the grid still holds a rat this bot could be shooting.
CALLED_TARGET_GONE = reading_binding(
    "calledTargetGone",
    [fleet_window(banner=DEAD, members=[MATE]),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

#: The same call with the target still on the grid -- the control for every
#: case above, since a rule that counted every reading would pass on the fixture
#: alone.
CALLED_TARGET_PRESENT = reading_binding(
    "calledTargetPresent",
    [fleet_window(banner=DEAD, members=[MATE]),
     overview([(DEAD, "Frigate", True, True), rat_row()]),
     drones_window(0),
     ship_ui()])

#: A second call, on a target that is on the grid. Following a stale call, this
#: is what a latch nothing cleared would ignore.
OTHER_TARGET_PRESENT = reading_binding(
    "otherTargetPresent",
    [fleet_window(banner=OTHER, members=[MATE]),
     overview([(OTHER, "Frigate", True, True), rat_row()]),
     drones_window(0),
     ship_ui()])

#: A second call, on a target that is also gone.
OTHER_TARGET_GONE = reading_binding(
    "otherTargetGone",
    [fleet_window(banner=OTHER, members=[MATE]),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

#: The banner calls a fleetmate. `actOnFleetBroadcast` refuses that above this
#: arm, so none of its readings may reach the budget.
CALLED_FLEETMATE = reading_binding(
    "calledFleetmate",
    [fleet_window(banner=MATE, members=[MATE]),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

#: A called acceleration gate whose row is in the tree and not drawn. #393
#: answers that on its own and it is not a name nothing carries.
CALLED_GATE_NOT_DRAWN = reading_binding(
    "calledGateNotDrawn",
    [fleet_window(banner=GATE, members=[MATE]),
     overview([rat_row(), gate_row(displayed=False)]),
     drones_window(0),
     ship_ui()])

#: No broadcast at all.
NO_BROADCAST = reading_binding(
    "noBroadcast",
    [fleet_window(members=[MATE]),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

READINGS = [CALLED_TARGET_GONE, CALLED_TARGET_PRESENT, OTHER_TARGET_PRESENT,
            OTHER_TARGET_GONE, CALLED_FLEETMATE, CALLED_GATE_NOT_DRAWN,
            NO_BROADCAST]


class TheReadingTheCounterIsForTest(unittest.TestCase):
    """`calledTargetWithNoOverviewRow`, over readings the real parser produced.

    This is the rule both the arm's precondition and the counter are, so every
    reading it declines is a reading the budget must not move on.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """Otherwise every case below passes against readings that decoded to
        `Nothing`, which is #174's own failure sitting in this file."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s /= Nothing" % name for name in
                 ("calledTargetGone", "calledTargetPresent",
                  "otherTargetPresent", "otherTargetGone", "calledFleetmate",
                  "calledGateNotDrawn", "noBroadcast")],
                READINGS),
            [True] * 7)

    def test_a_name_no_overview_row_carries_is_what_it_answers(self):
        """#395's own state: the target died and the banner did not."""
        self.assertEqual(
            self.repl.strings(["noRowFor calledTargetGone"],
                              [CALLED_TARGET_GONE]),
            [DEAD])

    def test_a_row_that_names_it_counts_nothing(self):
        """The control. A call the bot can act on spends none of the budget,
        which is what stops the give-up firing on a live target."""
        self.assertEqual(
            self.repl.strings(["noRowFor calledTargetPresent"],
                              [CALLED_TARGET_PRESENT]),
            ["-"])

    def test_a_call_the_arm_never_reaches_spends_nothing(self):
        """`actOnFleetBroadcast` refuses a called fleetmate above this arm, so
        those readings are not readings this arm spent -- #145's own defect is a
        counter measuring a quantity its give-up is not about."""
        self.assertEqual(
            self.repl.strings(["noRowFor calledFleetmate"],
                              [CALLED_FLEETMATE]),
            ["-"])

    def test_a_gate_row_that_is_not_drawn_is_not_a_missing_name(self):
        """#393 answers that state on its own, by handing the reading back. A
        counter that folded the two together would give up on a call it was
        already declining for a different and better reason."""
        self.assertEqual(
            self.repl.strings(["noRowFor calledGateNotDrawn"],
                              [CALLED_GATE_NOT_DRAWN]),
            ["-"])

    def test_no_broadcast_is_no_count(self):
        self.assertEqual(
            self.repl.strings(["noRowFor noBroadcast"], [NO_BROADCAST]),
            ["-"])


class TheCountIsKeptPerCallTest(unittest.TestCase):
    """`calledTargetGoneAfterReading`, folded over sessions.

    Asked as a fold rather than a reading at a time because a counter that is
    right for one reading and wrong across a session is exactly the defect this
    shape prevents.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def fold(self, names):
        return self.repl.strings(
            ["goneOver [%s]" % ", ".join('"%s"' % name for name in names)])[0]

    def test_the_count_climbs_while_the_name_names_nothing(self):
        self.assertEqual(self.fold([DEAD] * 5), "%s:5" % DEAD)

    def test_a_row_coming_back_clears_it(self):
        """The overview drawing the row again is the client saying the target is
        there, so the arm re-arms and the budget starts over."""
        self.assertEqual(self.fold([DEAD, DEAD, "-", DEAD]), "%s:1" % DEAD)

    def test_a_different_call_starts_its_own_count(self):
        """The half a bare counter cannot do, and the reason the name travels
        with the count: a second call must never be given up on with none of its
        own readings spent."""
        self.assertEqual(self.fold([DEAD] * 9 + [OTHER]), "%s:1" % OTHER)

    def test_the_banner_going_away_clears_it(self):
        self.assertEqual(self.fold([DEAD, DEAD, "-"]), "-")

    def test_a_quiet_session_records_nothing(self):
        self.assertEqual(self.fold(["-", "-", "-"]), "-")


class TheGiveUpIsBoundedTest(unittest.TestCase):
    """`calledTargetHasBeenGivenUpOn`, at its boundary and either side of it."""

    BOUND = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("calledTargetGoneReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdict(self, readings, name=None):
        return self.repl.evaluate(
            ['calledTargetHasBeenGivenUpOn "%s" (goneRecord "%s" %d)'
             % (DEAD, name or DEAD, count) for count in readings])

    def test_the_give_up_fires_one_reading_past_the_bound(self):
        self.assertEqual(self.verdict([self.BOUND, self.BOUND + 1]),
                         [False, True])

    def test_one_reading_of_it_is_not_a_verdict(self):
        """A fixed value beside the boundary pair, because a case that asks only
        about `constant` and `constant - 1` passes for any constant at all --
        including 0, which gives up on the first reading the row is missing."""
        self.assertEqual(self.verdict([1]), [False])

    def test_a_long_absence_is_still_a_verdict(self):
        self.assertEqual(self.verdict([50]), [True])

    def test_the_verdict_refuses_to_answer_for_another_name(self):
        """The memory update runs before the decision on the same reading, so
        the record cannot be about a different call -- but a rule that would
        answer anyway is one a later caller could ask from somewhere that does
        not hold."""
        self.assertEqual(self.verdict([50], name=OTHER), [False])

    def test_no_record_is_no_give_up(self):
        self.assertEqual(
            self.repl.evaluate(
                ['calledTargetHasBeenGivenUpOn "%s" Nothing' % DEAD]),
            [False])

    def test_the_bound_is_small_beside_the_bounds_on_a_click(self):
        """What this bounds is a reading with nothing to click, where
        `weaponsAskedReadingsBound` and `accelerationGateRefusesThisShipTicks`
        bound a click the client keeps refusing. A number in their range would
        be tens of readings of the whole bot held on a call it cannot act on,
        which is the defect rather than the fix."""
        weapons = int_constant("weaponsAskedReadingsBound")
        gate = int_constant("accelerationGateRefusesThisShipTicks")
        self.assertLess(self.BOUND, weapons)
        self.assertLess(self.BOUND, gate)
        self.assertGreater(self.BOUND, 1,
                           "one reading of an unparsed overview is not a "
                           "target that died")


class TheReadingFallsThroughTest(unittest.TestCase):
    """#360's property, carried: once there is nothing more to do about the
    call, the reading falls through.

    Asserted rather than "it stops re-locking", and with a control in the same
    call that must still act -- otherwise an arm answering `Nothing` for
    everything passes, which is the whole bot switched off.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("calledTargetGoneReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_reading_falls_through_once_the_call_is_stale(self):
        """The arm handed a spent budget, and the same grid with a fresh one as
        the control."""
        spent, fresh = self.repl.strings(
            ['broadcastArm { initBotMemory | calledTargetGone ='
             ' goneRecord "%s" (calledTargetGoneReadings + 1) }'
             " calledTargetGone" % DEAD,
             "broadcastArm initBotMemory calledTargetGone"],
            [CALLED_TARGET_GONE])
        self.assertEqual(spent, "FELL THROUGH")
        self.assertIn("Lock the called target '%s'." % DEAD, fresh)

    def test_the_grace_is_bounded_by_the_real_memory_update(self):
        """The counter, the verdict and the arm executed together: the shipped
        `updateMemoryForNewReadingFromGame` folded over a session of #395's own
        reading, and the shipped arm asked about the memory that fold left.

        One reading past the bound the arm hands the reading back; at the bound
        it is still trying, which is the control that keeps this about the bound
        rather than about the fold.
        """
        at_bound = ", ".join(["calledTargetGone"] * self.BOUND)
        past = ", ".join(["calledTargetGone"] * (self.BOUND + 1))
        held, released = self.repl.strings(
            ["broadcastArm (memoryOver [%s]) calledTargetGone" % at_bound,
             "broadcastArm (memoryOver [%s]) calledTargetGone" % past],
            [CALLED_TARGET_GONE])
        self.assertIn("Lock the called target '%s'." % DEAD, held)
        self.assertEqual(released, "FELL THROUGH")

    def test_the_session_really_counted_what_that_case_thinks(self):
        """Otherwise the case above passes on a fold that never advanced, which
        is a bound asserted against a counter that could not reach it -- #34's
        own shape."""
        self.assertEqual(
            self.repl.strings(
                ["goneAfter [%s]" % ", ".join(
                    ["calledTargetGone"] * (self.BOUND + 1))],
                [CALLED_TARGET_GONE]),
            ["%s:%d" % (DEAD, self.BOUND + 1)])

    def test_a_new_call_is_acted_on_after_a_stale_one_was_given_up_on(self):
        """The latch's clearing rule, end to end: a whole session spent giving
        up on a dead call, then the commander calls something that is on the
        grid, and the bot locks it on that reading."""
        session = ", ".join(
            ["calledTargetGone"] * (self.BOUND + 4) + ["otherTargetPresent"])
        self.assertIn(
            "Lock the called target '%s'." % OTHER,
            self.repl.strings(
                ["broadcastArm (memoryOver [%s]) otherTargetPresent" % session],
                [CALLED_TARGET_GONE, OTHER_TARGET_PRESENT])[0])

    def test_a_second_dead_call_spends_its_own_readings(self):
        """And the same session against a second call that is also gone: the arm
        is trying again rather than inheriting the first call's verdict."""
        session = ", ".join(
            ["calledTargetGone"] * (self.BOUND + 4) + ["otherTargetGone"])
        self.assertIn(
            "Lock the called target '%s'." % OTHER,
            self.repl.strings(
                ["broadcastArm (memoryOver [%s]) otherTargetGone" % session],
                [CALLED_TARGET_GONE, OTHER_TARGET_GONE])[0])

    def test_a_call_the_bot_can_act_on_is_untouched(self):
        """Whatever the memory holds, a called target with a row is locked --
        the give-up is scoped to the state it was measured on."""
        self.assertIn(
            "Lock the called target '%s'." % DEAD,
            self.repl.strings(
                ['broadcastArm { initBotMemory | calledTargetGone ='
                 ' goneRecord "%s" 900 } calledTargetPresent' % DEAD,
                 ],
                [CALLED_TARGET_PRESENT])[0])


class TheGiveUpIsVisibleTest(unittest.TestCase):
    """The give-up hands the reading back, and a `Nothing` carries no decision
    line -- so the status clause is the only thing that says it happened.

    Rendered from the rule's own answer rather than asserted by substring over
    the branch, which is the shape #109 records a clause passing a case while
    printing nothing at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("calledTargetGoneReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def clause(self, readings, name=None):
        return self.repl.strings(
            ['describeCalledTargetGone "%s" (goneRecord "%s" %d)'
             % (DEAD, name or DEAD, readings)])[0]

    def test_the_grace_says_how_far_it_has_got(self):
        clause = self.clause(2)
        self.assertIn("No row has named it for 2 of %d readings" % self.BOUND,
                      clause)

    def test_the_give_up_says_it_gave_up(self):
        clause = self.clause(self.BOUND + 1)
        self.assertIn("GIVEN UP ON after %d readings naming no row"
                      % (self.BOUND + 1), clause)
        self.assertIn("A new broadcast starts this over.", clause)

    def test_the_clause_says_nothing_about_another_call(self):
        self.assertEqual(self.clause(self.BOUND + 1, name=OTHER), "")

    def test_an_ordinary_call_says_nothing(self):
        """The commonest reading by far, and a clause on every one of them would
        be noise rather than a reading."""
        self.assertEqual(
            self.repl.strings(
                ['describeCalledTargetGone "%s" Nothing' % DEAD]),
            [""])

    def test_the_clause_is_in_the_status_line(self):
        """A rule nothing prints is a rule nobody reads."""
        given_up, present = self.repl.strings(
            ['describeCalled { initBotMemory | calledTargetGone ='
             ' goneRecord "%s" (calledTargetGoneReadings + 1) }'
             " calledTargetGone" % DEAD,
             "describeCalled initBotMemory calledTargetPresent"],
            [CALLED_TARGET_GONE, CALLED_TARGET_PRESENT])
        self.assertIn("GIVEN UP ON after", given_up)
        self.assertIn("NO OVERVIEW ROW names it", given_up,
                      "#393's own clause is still what says why")
        self.assertNotIn("GIVEN UP ON after", present)

    def test_the_status_line_calls_the_clause(self):
        self.assertIn(
            "describeCalledObject context",
            collapsed(declaration("statusTextFromState")))


class TheArmAndTheCounterReadOneRuleTest(unittest.TestCase):
    """Read out of the source, through a whitespace-collapsing reader.

    The parts a repl cannot reach: which rule the memory update asks, where the
    give-up is asked from, and that the unbounded wait it bounds is reachable
    from one state only.
    """

    def test_the_arm_and_the_counter_read_one_rule(self):
        """`updateMemoryForNewReadingFromGame` never sees a decision, so a
        restatement of the arm's precondition beside it is two rules that can
        disagree -- #145's own defect, and what `askingForTheCalledGateRecall`
        already avoids next door by asking the shipped rule."""
        update = collapsed(
            without_comments(declaration("updateMemoryForNewReadingFromGame")))
        self.assertIn("calledTargetGone = calledTargetGoneAfterReading "
                      "botMemoryBefore.calledTargetGone "
                      "(calledTargetWithNoOverviewRow", update)
        self.assertNotIn("CalledNameNamesNoOverviewRow", update,
                         "the classification belongs to the rule both readers "
                         "ask, not to a second copy in the memory update")

    def test_the_give_up_is_asked_before_the_lock(self):
        """The arm's own answer, so it can decline the reading;
        `lockCalledTarget` answers a `DecisionPathNode` and cannot."""
        arm = collapsed(
            without_comments(declaration("bringCalledTargetUnderFire")))
        self.assertIn(
            "CalledNameNamesNoOverviewRow -> if calledTargetHasBeenGivenUpOn "
            "calledTarget context.memory.calledTargetGone then Nothing "
            "else shootIt",
            arm)

    def test_the_unbounded_wait_is_reachable_from_one_state_only(self):
        """`lockCalledTarget`'s wait is one it cannot bound, since it answers a
        `DecisionPathNode` and a `DecisionPathNode` cannot decline a reading. It
        is reachable only where `calledObjectOnOverviewFromReading` answered
        `CalledNameNamesNoOverviewRow`, which is the branch above that bounds
        it: the other caller of `shootIt` has a row by construction.

        **#366 moved the branch and left the property.** That wait used to be
        the `Nothing` of a `case overviewEntryForPilot`; the lock now dispatches
        on `lockCalledTargetStep` and the wait is its
        `NoWayToLockTheCalledTarget` answer, which needs *neither* a banner to
        click nor a row -- strictly narrower than before, and still only
        reachable from the state #395 bounds.
        """
        lock = collapsed(without_comments(declaration("lockCalledTarget")))
        self.assertIn("NoWayToLockTheCalledTarget -> nothingToLockItWith", lock)
        self.assertIn("nothingToLockItWith = describeBranch", lock)
        self.assertIn("waitForProgressInGame", lock)
        self.assertIn("overviewEntryForPilot calledTarget "
                      "context.readingFromGameClient", lock)
        arm = collapsed(
            without_comments(declaration("bringCalledTargetUnderFire")))
        self.assertIn("CalledObjectIsNotAGate -> shootIt", arm)
        self.assertIn("overviewRowsForPilot pilotName readingFromGameClient "
                      "|> List.head",
                      collapsed(declaration("overviewEntryForPilot")))

    def test_the_counter_is_written_where_every_reading_reaches_it(self):
        """#102's placement rule: a counter and the comparison that reads it are
        two pieces of code on two schedules unless something makes them one.
        This one is advanced in the memory update, which runs unconditionally,
        and compared in an arm reached on the readings it counts."""
        self.assertIn("calledTargetGone =",
                      collapsed(declaration("updateMemoryForNewReadingFromGame")))
        self.assertIn("calledTargetGone = Nothing",
                      collapsed(declaration("initBotMemory")))

    def test_nothing_else_reads_the_memory_this_writes(self):
        """Two readers -- the arm and the status clause -- so a give-up decided
        in one place and reported in another cannot disagree, and no third
        branch starts deciding something else on a call's absence."""
        readers = [line.strip() for line in bot_source().splitlines()
                   if "context.memory.calledTargetGone" in line]
        self.assertEqual(len(readers), 2, readers)


if __name__ == "__main__":
    unittest.main()
