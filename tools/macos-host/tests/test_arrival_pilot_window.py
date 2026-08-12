"""Tests for the on-arrival pilot check being reachable, and for its bound.

Issue #194. `FoundOtherPilotOnArrival` has never been constructed in a recorded
run, and the reason is the trigger rather than the scanner. `weJustFinishedWarping`
demanded `shipIsWarping == Just False`, and `shipIsWarping` answers `Just False`
only while the client names some **other** maneuver. On the reading a warp ends
the client names none at all, so the transition is `Just True -> Nothing` and the
condition was unreachable in every recorded run. That left two things dead rather
than one: the leave branch, and the do-not-come-back half that reads the same
list to skip a scan result later.

**The transition is the case that was never executed**, which is how a total
defect survived in reachable code: nothing here or in the code it replaces ever
built a warp-end reading and asked whether the warp end was seen.
`TheWarpEndIsSeenOnTheShapeTheClientRenders` builds one, in the shape captured
off the live client during run 29 -- ship UI present, indication container
present, display texts holding only the location labels -- and folds two readings
through the real rules.

**The bound is one reading, and the corpus is why.** A neutral already there when
the ship lands means leave; a neutral arriving while the ship is fighting means
tough it out, so a rule that read `getNamesOfOtherPilotsInOverview` on every
reading would close #194 and open the opposite bug. The window this file was
first written around was 30 readings, to cover a probe-scanner lag that
`TheCorpusSaysWhereTheBoundBelongs` measures at zero -- and the same measurement
prices the 30: it would have recorded fifteen extra arrivals across four runs,
every one of them a pilot who was **not** on the grid when the ship landed.

The pure rules are executed through the real `Bot.elm` in `elm repl` rather than
restated here, and a whole session is folded through them by nesting the real
calls, which is the same composition the memory update performs. What is not an
expression -- where the snapshot sits, that the window's counter is advanced and
stored, that no decision reads the live overview -- is read out of
the source
through readers sliced by indentation, since the bindings under test build
record literals and a reader that stops at the opening brace has already cost
PRs #147, #156, #159 and #162 an assertion that passed having read nothing.

**Both apps, and only those two.** saxrat and the combat anomaly bot carry the
same `otherPilotsFoundOnArrival` and the same gate, so every rule below is asked
of both and the six shared declarations are compared byte for byte -- nothing
in them is app-specific, and a copy that drifted would still compile and still
answer. The mission runner has neither, which is asserted rather than assumed --
it does carry the same dead trigger for other purposes, which is #205 and not
this file.

**What could not be checked here.** Nothing has run: `FoundOtherPilotOnArrival`
has still never been constructed by either bot, so every claim below is about
what the rules answer and not about what a session did with the answer.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, collapsed, label, node, ship_ui, source_of)

COMBAT_ANOMALY_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-combat-anomaly-bot")
COMBAT_ANOMALY_BOT_ELM = os.path.join(COMBAT_ANOMALY_DIR, "Bot.elm")

# The bound as shipped, in readings. Written here as its own number so that a
# case can say the constant is this rather than merely that its own boundary
# pair is self-consistent -- a case asking only about `constant - 1` and
# `constant` passes for any constant at all, including one that admits
# everything, which is the hole four of #120's cases had.
#
# Zero means the arrival is the landing reading and no other, which is the
# single-reading snapshot #194 found dead, now on a trigger that fires.
# `TheCorpusSaysWhereTheBoundBelongs` is the measurement it is set from.
WINDOW_READINGS = 0

# A fixed value past any plausible retune of the bound. Anything out here is no
# longer "arrival" by any reading of the word, and is past every reading-counted
# bound these bots have.
CLEARLY_OUTSIDE_READINGS = 300

# The recorded saxrat runs the bound is measured against, and what they say.
# Recomputed by `TheCorpusSaysWhereTheBoundBelongs` rather than trusted here:
# these are the numbers the constant's doc comment quotes, and a case that only
# restated them would let them rot.
# What each recorded run says, per run rather than as a total, so a machine
# holding only some of them still checks the ones it has. `arrivals` is every
# reading on which `HOOOOONK in warp` stops; `named` is how many of those go on
# to name an anomaly before the next warp; `by_bound` is how many would record
# at least one pilot at each bound the constant could plausibly take.
CORPUS = {
    16: {"arrivals": 72, "named": 33,
         "by_bound": {0: 7, 1: 7, 3: 7, 10: 8, 30: 8}},
    21: {"arrivals": 8, "named": 1,
         "by_bound": {0: 1, 1: 1, 3: 1, 10: 2, 30: 3}},
    23: {"arrivals": 112, "named": 62,
         "by_bound": {0: 4, 1: 4, 3: 4, 10: 4, 30: 4}},
    24: {"arrivals": 58, "named": 27,
         "by_bound": {0: 7, 1: 7, 3: 8, 10: 11, 30: 19}},
}

# The measured lag between a warp ending and the probe scanner naming the
# anomaly, in readings. Zero, in every arrival across every run above that ever
# names one -- which is the whole of the case for the bound being what it is.
MEASURED_SCANNER_LAG_READINGS = 0

# The ship UI's indication container, captured off the live client during saxrat
# run 29 at 13:12:46 and 13:16:36. Two independent warps, identical shape: while
# warping the container names the manoeuvre, and on the reading the warp ends it
# is still there and holds only the location labels. That second list is the
# reading the whole of #194 turns on, and nothing had ever built one.
WARPING_INDICATION = ("Warp Drive Active",
                      "Destination: AreraDistance: 416 km",
                      "Mikhir",
                      "Sansha Hideaway")
LANDED_INDICATION = ("Mikhir", "Sansha Hideaway")

# The neighbouring bounds the constant's doc comment has to name, so that the
# number can be compared with them rather than converted in the reader's head.
# Two are required; these are the ones in range of it.
NEIGHBOURING_BOUNDS = ("approachIndicationTrustedForTicks",
                       "dockingRunInPatienceReadings",
                       "gateRefusesThisShipTicks",
                       "droneRecallGiveUpTicks")

# A name from run 23, quoted in issue #194.
PILOT = "Vladimir Barmin"
ANOTHER_PILOT = "Someone Else"

# The apps that carry this machinery. The mission runner has neither
# `otherPilotsFoundOnArrival` nor anything that would read it -- it flies
# mission pockets rather than anomalies -- and is out of scope.
APPS = (("saxrat", SAXRAT_BOT_ELM),
        ("combat anomaly bot", COMBAT_ANOMALY_BOT_ELM))

# The six declarations both apps carry, which are compared byte for byte
# rather than merely both being present.
SHARED_DECLARATIONS = ("shipWarpingFromReading",
                       "warpJustEnded",
                       "otherPilotArrivalWindowReadings",
                       "arrivalWindowIsOpen",
                       "otherPilotsFoundOnArrivalAfterReading",
                       "describeArrivalWindow")


class CombatAnomalyRepl(SaxratRepl):
    """The same harness and preamble, pointed at the combat anomaly bot."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "combat-anomaly-repl-")
        kwargs.setdefault("app_dir", COMBAT_ANOMALY_DIR)
        super().__init__(**kwargs)


def elm_list(names):
    return "[ %s ]" % ", ".join('"%s"' % name for name in names)


def elm_maybe_int(value):
    return "Nothing" if value is None else "Just %d" % value


def flying(indication_texts=None):
    """A ship UI, with an indication container holding `indication_texts`.

    `ship_ui` cannot express an indication, so the container is appended to what
    it builds. `None` leaves the container off entirely, which is a different
    reading from one holding no manoeuvre word -- and the captured warp-end
    reading is the second, not the first.
    """
    ui = ship_ui(100, 100, 4)
    if indication_texts is not None:
        ui["children"].append(
            node("IndicationContainer", {"_name": "indicationContainer"},
                 [label(text, (0, 60 + 18 * index, 200, 16))
                  for index, text in enumerate(indication_texts)],
                 region=(0, 60, 200, 100)))
    return ui


# The readings the transition is folded across, and one that carries no ship UI
# at all -- which answers `Nothing` for exactly the same reason the warp-end
# reading does, and must not be mistaken for it.
WARP_READINGS = (
    SaxratRepl.reading_binding("warping", [flying(WARPING_INDICATION)]),
    SaxratRepl.reading_binding("landed", [flying(LANDED_INDICATION)]),
    SaxratRepl.reading_binding("orbiting", [flying(["Orbiting"])]),
    SaxratRepl.reading_binding("noShipUI", []),
    # Answers `Maybe Bool`, never `Bool`: a fixture that failed to parse is then
    # `Nothing` and fails the case, rather than being defaulted into an answer
    # the reading never gave. #174 is the sweep of what that had cost.
    "warpEndSeen = \\before after -> Maybe.map2"
    " (\\b a -> warpJustEnded"
    " { warpingLastReading = shipWarpingFromReading b, readingNow = a })"
    " before after",
    # The condition this replaces, written out so a case can execute it on the
    # reading it had to answer `True` on.
    "oldWarpEndSeen = \\before after -> Maybe.map2"
    " (\\b a -> (shipWarpingFromReading b == Just True)"
    " && (shipWarpingFromReading a == Just False))"
    " before after",
    "shipUIPresentIn = \\reading -> reading"
    " |> Maybe.map (.shipUI >> (/=) Nothing)",
    "indicationPresentIn = \\reading -> reading"
    " |> Maybe.map (.shipUI >> Maybe.andThen .indication >> (/=) Nothing)",
    "warpingIn = \\reading -> reading |> Maybe.map shipWarpingFromReading",
)


def window_open(readings_since):
    return ("arrivalWindowIsOpen { readingsSinceWarpEnded = %s }"
            % elm_maybe_int(readings_since))


def after_reading(window_is_open, found_before, seen_now):
    """One call of the accumulation rule, with `found_before` an expression."""
    return ("otherPilotsFoundOnArrivalAfterReading { windowIsOpen = %s"
            ", foundBefore = %s, seenNow = %s }"
            % (window_is_open, found_before, elm_list(seen_now)))


def session(steps):
    """A whole session folded through the two real rules, as one expression.

    `steps` are `(readings since the warp ended, pilots on the overview)` in
    order, and each one is nested inside the next exactly as
    `updateMemoryForNewReadingFromGame` composes them: the window rule decides,
    the accumulation rule folds. Only the *advance* of `readingsSinceWarpEnded`
    is modelled here rather than executed, because it is a `let` binding in the
    memory update and not a rule; it is read out of the source instead, in
    `TheCounterAdvancesOnEveryReading`.
    """
    found = "[]"
    for readings_since, seen in steps:
        found = after_reading(window_open(readings_since), found, seen)
    return found


def without_block_comments(text):
    """The source with `{- ... -}` removed, so prose is not read as code.

    The doc comments here name the very functions the cases below count call
    sites of -- `getNamesOfOtherPilotsInOverview` appears in one of them to say
    why it must *not* be read on every reading -- and a case that counted those
    would report the opposite of what it means to.
    """
    return re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL)


def declaration_containing(source, needle_line_index):
    """The name of the top-level declaration a line falls in, or `None`."""
    annotation = re.compile(r"^([a-z][A-Za-z0-9_]*) :")
    for line in reversed(source.splitlines()[:needle_line_index + 1]):
        match = annotation.match(line)
        if match:
            return match.group(1)
    return None


def declarations_naming(source, name):
    """Every top-level declaration whose body mentions `name`, bar its own."""
    stripped = without_block_comments(source)
    lines = stripped.splitlines()
    found = []
    for index, line in enumerate(lines):
        if name not in line:
            continue
        owner = declaration_containing(stripped, index)
        if owner is None or owner == name:
            continue
        found.append(owner)
    return sorted(set(found))


def indented_binding(source, name):
    """One `let` binding's own lines, sliced by indentation.

    Ends at the next line indented no further than the binding's own name --
    the following binding, or the `in`. A reader that stops at the next
    ` <name> = ` stops at a *record literal* instead, and every binding under
    test here builds one.
    """
    lines = source.splitlines()
    opening = re.compile(r"^(\s+)%s =$" % re.escape(name))
    for index, line in enumerate(lines):
        match = opening.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        body = []
        for following in lines[index + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        return collapsed("\n".join(body))
    raise AssertionError("no let binding named %r" % name)


def body_of_declaration(source, name):
    match = re.search(r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
                      re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def record_returned_by(source, name):
    """What a `let ... in <record>` declaration actually answers with.

    Asserting over the whole declaration is not the same thing, and the
    difference is a mutation that survived: `, readingsSinceWarpEnded =
    readingsSinceWarpEnded` occurs **twice** in the memory update -- once in the
    record it returns and once as an argument to `arrivalWindowIsOpen` a few
    lines above -- so a case asserting that substring over the body passed with
    the memory field set to `Nothing`, which is the arrival counter advanced on
    every reading and stored on none. Assert the form, not the substring; #109's
    status clause, #122's trust rule and #145's named-button case each paid for
    this once already.
    """
    body = body_of_declaration(source, name)
    lines = body.splitlines()
    for index in reversed(range(len(lines))):
        if lines[index].rstrip() == "    in":
            return collapsed("\n".join(lines[index + 1:]))
    raise AssertionError("%r does not end in a `let ... in` record" % name)


class BothAppsRepl:
    """One repl per app carrying this machinery, so a failure names which."""

    REPLS = {"saxrat": SaxratRepl, "combat anomaly bot": CombatAnomalyRepl}

    @classmethod
    def setUpClass(cls):
        cls.repls = {app: open_repl(repl_class)
                     for app, repl_class in cls.REPLS.items()}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.evaluate(expressions, definitions)


class TheWindowOpensAndCloses(BothAppsRepl, unittest.TestCase):
    """`arrivalWindowIsOpen`, executed at its boundary and either side of it.

    The boundary pair alone would pass for any constant, so a fixed value well
    outside is asked too, and `TheBoundIsTheOneThatShipped` pins the constant
    itself.
    """

    def test_the_reading_the_warp_ends_on_is_arrival(self):
        """The single-reading trigger this replaces, subsumed rather than lost.

        Zero readings elapsed is the reading `weJustFinishedWarping` used to be
        the only answer for, so nothing the old code recorded is refused by the
        new rule.
        """
        for app, answers in self.each([window_open(0)]):
            self.assertEqual(
                answers, [True],
                "%s does not count the warp-end reading itself as arrival, so "
                "the fix refuses what the code it replaces accepted" % app)

    def test_a_reading_exactly_on_the_bound_is_still_arrival(self):
        """The comparison moved one reading tighter fails here."""
        for app, answers in self.each([window_open(WINDOW_READINGS)]):
            self.assertEqual(
                answers, [True],
                "%s's comparison is off by one at the bound" % app)

    def test_a_reading_past_the_bound_is_not_arrival(self):
        """The half that makes this a window rather than a live check.

        A pilot who turns up here is the mid-fight case #194 exists to keep
        behaving as it does today, so a rule answering `True` here is the
        opposite bug rather than a loose bound. The comparison moved one reading
        looser fails on the first of these.
        """
        for app, answers in self.each([
                window_open(WINDOW_READINGS + 1),
                window_open(CLEARLY_OUTSIDE_READINGS)]):
            self.assertEqual(
                answers, [False] * 2,
                "%s's arrival window never closes, so a pilot arriving "
                "mid-fight would arm the leave branch" % app)

    def test_the_rule_is_a_bound_and_not_an_equality_on_zero(self):
        """The bound is one reading, and it is still written as a bound.

        A rule spelled `readingsSinceWarpEnded == Just 0` answers identically
        today and quietly stops being a window: widening it would then mean
        rewriting the comparison rather than changing the number the doc comment
        argues for, and the argument would be nowhere near the change.
        """
        for app, path in APPS:
            rule = collapsed(without_block_comments(
                body_of_declaration(source_of(path), "arrivalWindowIsOpen")))
            self.assertIn(
                "readings <= otherPilotArrivalWindowReadings", rule,
                "%s no longer compares against the bound, so the bound is no "
                "longer where the window is decided" % app)

    def test_no_warp_this_session_is_a_closed_window(self):
        """`Nothing` must not read as "we have always just arrived"."""
        for app, answers in self.each([window_open(None)]):
            self.assertEqual(
                answers, [False],
                "%s treats a session that has not warped as one permanent "
                "arrival" % app)


class TheBoundIsTheOneThatShipped(BothAppsRepl, unittest.TestCase):
    """The constant itself, so a boundary pair cannot pass for any value.

    The unit is readings, which is what every other bound in these bots is
    counted in -- so the constant's own doc comment has to place it among its
    neighbours rather than leaving a reader to convert. Confusing this unit with
    a clock has cost this repo a threshold calibration twice, a retreat
    measurement once, and an issue's whole diagnosis once.
    """

    def test_the_window_is_the_landing_reading_and_no_other(self):
        for app, answers in self.each(
                ["otherPilotArrivalWindowReadings == %d" % WINDOW_READINGS]):
            self.assertEqual(
                answers, [True],
                "%s's arrival window is not the one reading the corpus "
                "supports" % app)

    def test_the_window_is_no_wider_than_the_lag_it_exists_to_cover(self):
        """The window was built to outlast the scanner naming the anomaly.

        Measured, that lag is zero readings -- the anomaly is named on the
        warp-end reading in every arrival that ever names one -- so a bound
        above it buys nothing and costs the mid-fight case. The measurement is
        recomputed in `TheCorpusSaysWhereTheBoundBelongs`; this is the constant
        being held to it.
        """
        for app, answers in self.each([
                "otherPilotArrivalWindowReadings <= %d"
                % MEASURED_SCANNER_LAG_READINGS]):
            self.assertEqual(
                answers, [True],
                "%s's arrival window is wider than the probe-scanner lag it "
                "exists to cover, so the readings it adds can only record "
                "pilots who were not there when the ship landed" % app)

    def test_the_window_is_narrower_than_a_fight(self):
        for app, answers in self.each([
                "otherPilotArrivalWindowReadings < %d"
                % CLEARLY_OUTSIDE_READINGS]):
            self.assertEqual(
                answers, [True],
                "%s's arrival window is wide enough to cover a whole "
                "engagement, which is the mid-fight case rather than arrival"
                % app)

    def test_the_constant_names_a_neighbouring_reading_count_bound(self):
        """The unit's whole benefit, asserted where the reader meets it.

        A reading count is worth having over a clock here precisely because it
        is comparable to the other bounds in these bots without any conversion.
        That is only true if the doc comment names some of them, so it does --
        at least two, and it says "readings" in words.
        """
        for app, path in APPS:
            match = re.search(
                r"\{-\|(?:(?!-\}).)*?-\}\s*\notherPilotArrivalWindowReadings :",
                source_of(path), re.DOTALL)
            self.assertTrue(
                match,
                "%s's arrival window constant has no doc comment" % app)
            prose = collapsed(match.group(0))
            self.assertIn(
                "readings", prose,
                "%s's arrival window does not say what unit it is in" % app)
            named = [bound for bound in NEIGHBOURING_BOUNDS if bound in prose]
            self.assertGreaterEqual(
                len(named), 2,
                "%s's arrival window names %d of the reading-counted bounds it "
                "should be compared against, so a reader cannot tell whether 30 "
                "is long or short" % (app, len(named)))

    def test_the_constant_records_what_a_wider_bound_would_cost(self):
        """The measurement, carried where the number is, not only in a PR.

        The bound is the whole of this feature's risk, and the case for it is a
        count off the corpus: widening to 30 readings would record fifteen more
        arrivals across four runs, all of them pilots who were not on the grid
        when the ship landed. A doc comment that dropped that leaves the next
        reader with a bare number and the impression that raising it is free.

        Asserted on the measurement's own words rather than on a slogan, because
        a slogan survives the substance being deleted -- which is exactly what
        this case's predecessor let through once.
        """
        for app, path in APPS:
            match = re.search(
                r"\{-\|(?:(?!-\}).)*?-\}\s*\notherPilotArrivalWindowReadings :",
                source_of(path), re.DOTALL)
            prose = collapsed(match.group(0))
            self.assertIn(
                "median 0", prose,
                "%s's arrival window does not record the lag it was built to "
                "cover being measured at zero, which is the reason the bound "
                "is what it is" % app)
            self.assertIn(
                "already fighting", prose,
                "%s's arrival window does not say what the readings past the "
                "landing one would record, which is the cost of widening it"
                % app)
            self.assertIn(
                "wall-clock", prose,
                "%s's arrival window does not price its unit against the clock,"
                " so a reader cannot tell what 30 readings had been worth"
                % app)


class ThePilotsAccumulateWhileTheWindowIsOpen(BothAppsRepl, unittest.TestCase):
    """`otherPilotsFoundOnArrivalAfterReading`, at each of its clauses."""

    def test_an_open_window_records_who_is_on_the_grid(self):
        for app, answers in self.each([
                "%s == %s" % (after_reading("True", "[]", [PILOT]),
                              elm_list([PILOT]))]):
            self.assertEqual(
                answers, [True],
                "%s records nobody on a reading inside the arrival window, "
                "which is issue #194 unfixed" % app)

    def test_a_closed_window_records_nobody(self):
        for app, answers in self.each([
                "%s == []" % after_reading("False", "[]", [PILOT])]):
            self.assertEqual(
                answers, [True],
                "%s records a pilot after the arrival window closed, which is "
                "the mid-fight bug #194 exists to prevent" % app)

    def test_a_closed_window_leaves_what_arrival_found(self):
        """Closing must not unsay the verdict; it must stop adding to it."""
        for app, answers in self.each([
                "%s == %s" % (after_reading("False", elm_list([PILOT]), []),
                              elm_list([PILOT]))]):
            self.assertEqual(
                answers, [True],
                "%s forgets who was found on arrival once the window closes, "
                "so the do-not-come-back half stays dead" % app)

    def test_a_pilot_who_leaves_inside_the_window_is_still_recorded(self):
        """Accumulate rather than overwrite, which is the latch.

        The snapshot this replaces ran on one reading, so what it wrote was
        final. A window whose readings each *replaced* the list would forget a
        pilot who was on the grid when the ship landed and warped off two
        readings later -- and forgetting is exactly the half #194 says is dead,
        since the same list is what skips the scan result later.
        """
        for app, answers in self.each([
                "%s == %s" % (session([(0, [PILOT]), (1, []), (2, [])]),
                              elm_list([PILOT]))]):
            self.assertEqual(
                answers, [True],
                "%s overwrites the arrival list each reading, so a pilot who "
                "warps off inside the window is unsaid" % app)

    def test_a_name_is_recorded_once(self):
        for app, answers in self.each([
                "%s == %s" % (session([(0, [PILOT]), (1, [PILOT]),
                                       (2, [PILOT])]),
                              elm_list([PILOT]))]):
            self.assertEqual(
                answers, [True],
                "%s records the same pilot once per reading of the window"
                % app)

    def test_the_first_pilot_seen_is_named_first(self):
        """`findReasonToAvoidAnomalyFromMemory` reports the head of this list.

        The pilot who was already there when the ship landed is the one an
        operator wants named, so order is first-seen first. Asked of the
        accumulation rule with the window held open across both readings, since
        at the bound that shipped the second reading is already outside it --
        the ordering is the rule's own and has to survive a widening that a
        later corpus could argue for.
        """
        for app, answers in self.each([
                "%s == %s" % (after_reading(
                    "True",
                    after_reading("True", "[]", [PILOT]),
                    [PILOT, ANOTHER_PILOT]),
                    elm_list([PILOT, ANOTHER_PILOT]))]):
            self.assertEqual(
                answers, [True],
                "%s does not keep the pilot found first at the head of the "
                "list the leave branch reports" % app)


class AWholeSessionFoldedThroughTheRules(BothAppsRepl, unittest.TestCase):
    """The composition the memory update performs, over readings in order.

    This is the shape #194 describes: warp ends, the scanner says nothing for
    several readings, and only then names the anomaly. The old code recorded
    nothing on any of them.
    """

    def test_the_pilot_on_the_landing_reading_is_recorded(self):
        """The arrival as the corpus actually has it.

        The anomaly is named on the warp-end reading, so the fold starts at
        reading zero -- and the pilot standing there is recorded and then left
        alone for every reading after, which is the do-not-come-back half.
        """
        landing = [(0, [PILOT]), (1, [PILOT]), (2, [PILOT])]
        for app, answers in self.each([
                "%s == %s" % (session(landing), elm_list([PILOT]))]):
            self.assertEqual(
                answers, [True],
                "%s records nobody for a pilot standing on the grid when the "
                "ship landed, which is exactly #194" % app)

    def test_a_pilot_arriving_after_the_window_is_not_recorded(self):
        """The fight the bot must stay in."""
        during_the_fight = [(4, []), (WINDOW_READINGS + 10, [PILOT]),
                            (WINDOW_READINGS + 40, [PILOT])]
        for app, answers in self.each([
                "%s == []" % session(during_the_fight)]):
            self.assertEqual(
                answers, [True],
                "%s arms the leave branch for a pilot who warped in while the "
                "bot was fighting" % app)

    def test_a_scanner_that_never_catches_up_inside_the_window_records_nobody(
            self):
        """Stated rather than hidden: the window can still be too short.

        If the scanner does not name the anomaly until after the bound, this fix
        is inert for that arrival and the bot behaves as it does today. Measured,
        that has never happened -- the anomaly is named on the warp-end reading
        in all 123 arrivals across four runs that ever name one -- but the rule
        answers this way if it ever does, and it is a bound the corpus could
        move.
        """
        for app, answers in self.each([
                "%s == []" % session([(WINDOW_READINGS + 1, [PILOT])])]):
            self.assertEqual(
                answers, [True],
                "%s records an arrival the window had already closed on" % app)


class TheStatusLineSaysWhichWayItIsInert(BothAppsRepl, unittest.TestCase):
    """`describeArrivalWindow`, rendered at each of its shapes.

    Nothing about the window was visible on a reading before this, which is most
    of why #194 needed a corpus sweep to find. The clause has to separate the
    three ways the feature can still be inert, so an operator can tell them
    apart on a single line.
    """

    def render(self, since, is_open, found):
        return ("describeArrivalWindow { readingsSinceWarpEnded = %s"
                ", windowIsOpen = %s, otherPilotsFoundOnArrival = %s }"
                % (elm_maybe_int(since),
                   "True" if is_open else "False",
                   "Nothing" if found is None else "Just " + elm_list(found)))

    def rendered(self, app, since, is_open, found):
        return self.repls[app].strings([self.render(since, is_open, found)])[0]

    def test_a_session_that_has_not_warped_says_so(self):
        for app in self.repls:
            clause = self.rendered(app, None, False, None)
            self.assertIn(
                "no warp has finished", clause,
                "%s does not say when the window has never opened, which is "
                "what #194 looked like from outside for every recorded run"
                % app)

    def test_an_open_window_says_so_with_both_numbers(self):
        for app in self.repls:
            clause = self.rendered(app, WINDOW_READINGS, True, [])
            self.assertIn("OPEN", clause,
                          "%s does not say the window is open" % app)
            self.assertIn("%d of %d readings" % (WINDOW_READINGS,
                                                 WINDOW_READINGS), clause,
                          "%s does not say how many readings since the warp "
                          "against the bound, so a reader cannot tell how "
                          "close it is -- nor that the unit is readings" % app)

    def test_a_closed_window_is_not_reported_as_open(self):
        for app in self.repls:
            clause = self.rendered(app, 91, False, [])
            self.assertIn("closed", clause,
                          "%s reports a closed window as open" % app)
            self.assertNotIn("OPEN", clause,
                             "%s reports a closed window as open" % app)

    def test_no_anomaly_named_is_distinct_from_nobody_found(self):
        """#194's own diagnosis, made visible on the reading it happens.

        These are the two states the old code could not be told apart in: an
        anomaly whose arrival found nobody, and an anomaly the scanner has not
        named so nothing can be recorded at all.
        """
        for app in self.repls:
            unnamed = self.rendered(app, 1, True, None)
            empty = self.rendered(app, 1, True, [])
            self.assertNotEqual(
                unnamed, empty,
                "%s prints the same clause whether the scanner has named the "
                "anomaly or not, which is the state #194 hid in" % app)
            self.assertIn(
                "no anomaly named", unnamed,
                "%s does not say the scanner has named no anomaly" % app)

    def test_a_recorded_pilot_is_named(self):
        for app in self.repls:
            clause = self.rendered(app, 1, True, [PILOT])
            self.assertIn(
                PILOT, clause,
                "%s does not name the pilot the leave branch is about to fire "
                "on" % app)


class TheWarpEndIsSeenOnTheShapeTheClientRenders(
        BothAppsRepl, unittest.TestCase):
    """The transition itself, which nothing had ever executed.

    That is how a defect this total survived in reachable code: every case this
    file shipped with, and the code before it, asked about the window and the
    accumulation and never about whether a warp ending is noticed. The rule was
    `shipWarpingInLastReading == Just True` and `shipIsWarping == Just False`,
    and the client renders no manoeuvre word at all when a warp ends -- so the
    transition is `Just True -> Nothing`, the condition could not fire, and
    every case downstream of it passed anyway.

    The readings here go through the real `EveOnline.ParseUserInterface`, in the
    shape captured off the live client during run 29: the indication container
    is **present** on the warp-end reading and holds only the location labels.
    A fixture that left the container off entirely would answer `Nothing` too,
    for a different reason, and would have let a fix that only handled the
    missing container pass.
    """

    def test_the_fixtures_are_the_readings_the_client_rendered(self):
        """Checked before anything is concluded from them.

        A tree the parser makes nothing of answers `Nothing` for the same rule
        the warp-end reading does, so the case below it would pass having
        asserted about an empty fixture rather than about a warp.
        """
        for app, answers in self.each([
                "warpingIn warping == Just (Just True)",
                "shipUIPresentIn landed == Just True",
                "indicationPresentIn landed == Just True",
                "warpingIn landed == Just Nothing",
                "warpingIn orbiting == Just (Just False)",
                "shipUIPresentIn noShipUI == Just False",
        ], WARP_READINGS):
            self.assertEqual(
                answers, [True] * 6,
                "%s's fixtures are not the readings this file says they are: "
                "the warp-end reading must carry a ship UI and an indication "
                "container and name no manoeuvre" % app)

    def test_a_warp_ending_into_stillness_is_seen(self):
        """The case #194 is, and the one nothing had ever run."""
        for app, answers in self.each(
                ["warpEndSeen warping landed == Just True"], WARP_READINGS):
            self.assertEqual(
                answers, [True],
                "%s does not notice a warp ending when the client stops naming "
                "a manoeuvre, which is what the client actually does -- so the "
                "arrival window never opens and nothing downstream of it can "
                "fire" % app)

    def test_the_condition_this_replaces_would_have_missed_it(self):
        """The defect, executed on the reading it had to answer `True` on.

        Kept as its own case rather than left as history: it is the only thing
        in this file that fails if somebody restores the old shape, and it fails
        with the reason rather than with an arithmetic mismatch six rules away.
        """
        for app, answers in self.each(
                ["oldWarpEndSeen warping landed == Just False"], WARP_READINGS):
            self.assertEqual(
                answers, [True],
                "%s's `Just False` condition now answers `True` at the end of a "
                "warp, which the captured client reading says it cannot -- so "
                "this case is measuring something other than #194" % app)

    def test_a_warp_ending_into_another_manoeuvre_is_still_seen(self):
        """The one shape the old condition did handle, not lost in the fix."""
        for app, answers in self.each(
                ["warpEndSeen warping orbiting == Just True"], WARP_READINGS):
            self.assertEqual(
                answers, [True],
                "%s no longer notices a warp that ends straight into another "
                "manoeuvre, which is the only end of warp the old condition "
                "could see" % app)

    def test_a_reading_with_no_ship_ui_is_not_an_arrival(self):
        """The half of `Nothing` that must not count.

        `shipWarpingFromReading` answers `Nothing` both for a ship that stopped
        manoeuvring and for a reading that could not see the ship at all --
        docked, a client that did not render, a reading across a session change.
        A fix written as `/= Just True` and nothing else would call every one of
        those an arrival, and the bot would take an arrival snapshot of a grid
        it never landed on.
        """
        for app, answers in self.each(
                ["warpEndSeen warping noShipUI == Just False"], WARP_READINGS):
            self.assertEqual(
                answers, [True],
                "%s treats a reading with no ship UI as a warp ending, so a "
                "client that failed to render one arms the arrival snapshot"
                % app)

    def test_a_reading_still_in_warp_is_not_an_arrival(self):
        for app, answers in self.each(
                ["warpEndSeen warping warping == Just False"], WARP_READINGS):
            self.assertEqual(
                answers, [True],
                "%s calls every reading of a warp its end" % app)

    def test_a_session_that_was_not_warping_before_is_not_an_arrival(self):
        """`Nothing -> Nothing` is not a warp ending either.

        `shipWarpingInLastReading` stores the same three-valued answer, so the
        first readings of a session -- and any run of readings the client could
        not be seen through -- are `Nothing` before and `Nothing` after. Nothing
        ended, and the counter must not restart.
        """
        for app, answers in self.each([
                "warpEndSeen noShipUI landed == Just False",
                "warpEndSeen noShipUI noShipUI == Just False",
                "warpEndSeen landed landed == Just False",
        ], WARP_READINGS):
            self.assertEqual(
                answers, [True] * 3,
                "%s restarts the arrival counter on a session that has not "
                "warped, which makes every reading an arrival" % app)


def saxrat_runs(*numbers):
    """The recorded saxrat runs this machine has, or the shared skip.

    saxrat's logs are named differently from the mission runner's, so
    `prerequisites.recorded_runs` does not reach them; this is the wording every
    other saxrat corpus case already skips with, and `check_expected_skips.py`
    refuses a second spelling of it.
    """
    found = [(number, os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number))
             for number in numbers]
    found = [pair for pair in found if os.path.exists(pair[1])]
    if not found:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs say "
            "about the arrival window's bound cannot be consulted here")
    return found


def status_blocks(path):
    """Every status block in a recorded run, as its own list of lines."""
    block = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("--------"):
                if block:
                    yield block
                block = []
            else:
                block.append(line.rstrip("\n"))
    if block:
        yield block


def arrivals_in(path):
    """Every warp-end reading in a recorded run, and what followed it.

    `HOOOOONK in warp` is the decision saxrat prints while
    `shipUIIndicatesShipIsWarpingOrJumping`, so the first block after a run of
    them is the reading the warp ended on -- the same reading `warpJustEnded`
    fires on, read off the same manoeuvre indication.

    Each arrival answers `(readings until an anomaly is named, the pilots seen
    on each reading)`, both truncated at the next warp: the anomaly the ship
    arrived in is over by then, and reading past it would credit a bound with
    readings belonging to somewhere else. The gap is `None` when no anomaly is
    ever named, which no bound reaches.
    """
    status = re.compile(
        r"^Current anomaly: (.*?)\. Seeing \d+ other pilots in the overview"
        r"(?:: (.*?))?\.\s*$")
    readings = []
    for block in status_blocks(path):
        matched = None
        for text in block:
            found = status.match(text)
            if found:
                matched = found
        if matched is None:
            continue
        pilots = set()
        if matched.group(2):
            pilots = {name.strip() for name in matched.group(2).split(",")
                      if name.strip()}
        readings.append((
            any(text.startswith("+ HOOOOONK in warp") for text in block),
            matched.group(1),
            pilots))

    arrivals = []
    for index in range(1, len(readings)):
        if not (readings[index - 1][0] and not readings[index][0]):
            continue
        gap = None
        pilots_by_reading = []
        for ahead in range(index, len(readings)):
            if readings[ahead][0]:
                break
            pilots_by_reading.append(readings[ahead][2])
            if gap is None and readings[ahead][1] != "None":
                gap = ahead - index
        arrivals.append((gap, pilots_by_reading))
    return arrivals


def arrivals_recording_a_pilot(arrivals, bound):
    """How many of `arrivals` a window of `bound` readings would record."""
    return sum(1 for _, pilots in arrivals
               if set().union(*pilots[:bound + 1]))


class TheCorpusSaysWhereTheBoundBelongs(unittest.TestCase):
    """The measurement the bound is set from, recomputed rather than quoted.

    The window was first written at 30 readings to outlast the probe scanner
    naming the anomaly. Both halves of that are measurable off the recorded runs
    and neither had been measured: the lag is zero, and the readings a wider
    bound adds record pilots who were not on the grid when the ship landed --
    the mid-fight case the feature exists to refuse.

    These read the recorded runs and only read them. On a machine with none they
    skip with the wording every other saxrat corpus case uses; on CI, which has
    none, that is what happens.
    """

    def test_the_scanner_names_the_anomaly_on_the_warp_end_reading(self):
        """The premise the window was built on, and it is not there.

        Not "usually zero": zero in every arrival that ever names an anomaly, in
        every run. A single arrival with a gap of one would be an argument for a
        wider bound, and there is not one.
        """
        for number, path in saxrat_runs(*sorted(CORPUS)):
            arrivals = arrivals_in(path)
            gaps = [gap for gap, _ in arrivals if gap is not None]
            self.assertEqual(
                len(arrivals), CORPUS[number]["arrivals"],
                "saxrat run %d no longer has the warp endings this bound was "
                "measured over" % number)
            self.assertEqual(
                len(gaps), CORPUS[number]["named"],
                "saxrat run %d no longer names an anomaly after the arrivals "
                "this bound was measured over" % number)
            self.assertEqual(
                max(gaps), MEASURED_SCANNER_LAG_READINGS,
                "saxrat run %d has an arrival where the probe scanner named "
                "the anomaly %d readings after the warp ended, so the bound of "
                "%d readings is no longer wide enough for the corpus it was "
                "set from" % (number, max(gaps), WINDOW_READINGS))

    def test_a_wider_bound_would_only_record_pilots_who_were_not_there(self):
        """The price of the 30 readings this shipped with, in arrivals.

        Every arrival a wider bound adds is one where the overview held nobody
        on the reading the ship landed and somebody afterwards -- which is a
        pilot who arrived while the bot was already fighting, and the one thing
        #194 says must not arm the leave branch.
        """
        for number, path in saxrat_runs(*sorted(CORPUS)):
            arrivals = arrivals_in(path)
            recorded = {bound: arrivals_recording_a_pilot(arrivals, bound)
                        for bound in CORPUS[number]["by_bound"]}
            self.assertEqual(
                recorded, CORPUS[number]["by_bound"],
                "saxrat run %d no longer records what the bound was chosen "
                "against" % number)
            self.assertEqual(
                recorded[0], recorded[1],
                "saxrat run %d has an arrival where a pilot appeared on the "
                "reading after the ship landed, which is the one thing a bound "
                "of more than zero could honestly buy" % number)
            self.assertGreaterEqual(
                recorded[30], recorded[WINDOW_READINGS],
                "saxrat run %d records no more at 30 readings than at the "
                "bound that shipped, so this case is no longer pricing "
                "anything" % number)


class TheSnapshotStillNeedsTheScannerAndTheSameKey(unittest.TestCase):
    """The two things this change deliberately does not do.

    The other half of #194's "which side to move" was to make the snapshot
    independent of the scanner naming the anomaly. That is not what shipped: the
    memory keying is untouched and the snapshot still sits inside the branch
    that has an anomaly ID to file it under.
    """

    def test_the_snapshot_is_inside_the_branch_that_names_the_anomaly(self):
        for app, path in APPS:
            update = body_of_declaration(
                without_block_comments(source_of(path)),
                "updateMemoryForNewReadingFromGame")
            binding = indented_binding(update, "visitedAnomalies")
            self.assertIn(
                "getCurrentAnomalyIDAsSeenInProbeScanner", binding,
                "%s no longer asks the probe scanner before writing anomaly "
                "memory" % app)
            self.assertIn(
                "otherPilotsFoundOnArrivalAfterReading", binding,
                "%s takes the arrival snapshot outside the anomaly-memory "
                "update, which is the other design #194 offered and not this "
                "one" % app)

    def test_the_memory_is_still_keyed_by_the_anomaly_id(self):
        for app, path in APPS:
            update = body_of_declaration(
                without_block_comments(source_of(path)),
                "updateMemoryForNewReadingFromGame")
            binding = indented_binding(update, "visitedAnomalies")
            self.assertIn(
                "Dict.insert currentAnomalyID", binding,
                "%s no longer files anomaly memory under the anomaly's own id"
                % app)

    def test_the_snapshot_is_no_longer_gated_on_the_warp_end_reading(self):
        """The defect itself: both conditions on one reading.

        The window is what replaced it, so a `weJustFinishedWarping` test back
        inside this binding's snapshot is #194 restored.
        """
        for app, path in APPS:
            update = body_of_declaration(
                without_block_comments(source_of(path)),
                "updateMemoryForNewReadingFromGame")
            snapshot = indented_binding(
                update, "anomalyMemoryWithOtherPilotsOnArrival")
            self.assertNotIn(
                "weJustFinishedWarping", snapshot,
                "%s gates the arrival snapshot on the warp-end reading again, "
                "which is the mutual exclusion #194 is about" % app)
            self.assertIn(
                "arrivalWindowIsOpenNow", snapshot,
                "%s does not hand the snapshot the window's verdict" % app)

    def test_the_leave_branch_still_reads_the_list(self):
        """The consumer, so the fix cannot be wired to nothing."""
        for app, path in APPS:
            branch = body_of_declaration(
                without_block_comments(source_of(path)),
                "findReasonToAvoidAnomalyFromMemory")
            self.assertIn("otherPilotsFoundOnArrival", collapsed(branch),
                          "%s's leave branch no longer reads the arrival list"
                          % app)
            self.assertIn("FoundOtherPilotOnArrival", collapsed(branch),
                          "%s's leave branch no longer answers with the "
                          "reason #194 says has never been constructed" % app)


class TheCounterAdvancesOnEveryReading(unittest.TestCase):
    """`readingsSinceWarpEnded`, which is not a rule and so is read.

    It restarts at zero on the one reading a warp ends and advances on every
    other, and it lives in `updateMemoryForNewReadingFromGame` because that is
    the only thing that runs on every reading unconditionally -- #102's and
    #126's placement rule, and what makes a reading count meaningful at all. A
    version that wrote `Nothing` on the readings in between would close the
    window on the reading after the warp, which is #194 with one extra reading
    of coverage; one that did not advance would hold it open forever, which is
    the mid-fight bug.
    """

    def test_it_restarts_on_the_warp_end_and_advances_otherwise(self):
        for app, path in APPS:
            update = body_of_declaration(
                without_block_comments(source_of(path)),
                "updateMemoryForNewReadingFromGame")
            binding = indented_binding(update, "readingsSinceWarpEnded")
            self.assertIn("weJustFinishedWarping", binding,
                          "%s does not restart the arrival counter when a warp "
                          "ends" % app)
            self.assertIn("Just 0", binding,
                          "%s does not restart the arrival counter at zero, so "
                          "the warp-end reading is not itself arrival" % app)
            self.assertIn("botMemoryBefore.readingsSinceWarpEnded", binding,
                          "%s does not carry the arrival counter forward, so "
                          "the window closes on the reading after the warp"
                          % app)
            self.assertIn("Maybe.map ((+) 1)", binding,
                          "%s does not advance the arrival counter, so the "
                          "window never closes" % app)

    def test_it_is_written_to_memory_on_every_reading(self):
        """Asserted over the record the update *returns*, not over its body.

        The same text occurs a few lines above as an argument to
        `arrivalWindowIsOpen`, so a case reading the whole declaration passes
        with the memory field pinned at `Nothing` -- the counter advanced on
        every reading and stored on none, which is the window never opening
        again after the warp's own reading.
        """
        for app, path in APPS:
            record = record_returned_by(
                without_block_comments(source_of(path)),
                "updateMemoryForNewReadingFromGame")
            self.assertIn(
                ", readingsSinceWarpEnded = readingsSinceWarpEnded", record,
                "%s advances the arrival counter and does not store it, so the "
                "window can never be open on any reading but the warp's" % app)


class NoDecisionReadsTheLiveOverview(unittest.TestCase):
    """The rule #194 forbids by name, pinned as a count of readers.

    "Checking `getNamesOfOtherPilotsInOverview` on every reading would close
    this bug and introduce the opposite one." So the live read stays where it
    was: the memory update, which is bounded by the window, and the status line,
    which decides nothing. A third reader is where the opposite bug would
    arrive, and it has to be argued for rather than added.
    """

    ALLOWED = {"updateMemoryForNewReadingFromGame", "statusTextFromState"}

    def test_only_the_memory_update_and_the_status_line_read_it(self):
        for app, path in APPS:
            readers = set(declarations_naming(
                source_of(path), "getNamesOfOtherPilotsInOverview"))
            self.assertEqual(
                readers, self.ALLOWED,
                "%s reads the live list of other pilots in %s -- a decision "
                "reading it is the mid-fight bug #194 exists to refuse"
                % (app, sorted(readers - self.ALLOWED) or "nowhere"))

    def test_the_status_clause_is_rendered_from_the_rule(self):
        """Not inlined, so a case can execute what an operator reads.

        And asserted **into the list that gets printed**, not merely into the
        declaration. A mutation that left the binding in place and dropped it
        from the list survived a case asserting the latter: the clause computed
        on every reading and shown on none, which is this repo's signature bug
        arriving inside the instrument built to make the bug visible.
        """
        for app, path in APPS:
            status = collapsed(body_of_declaration(
                without_block_comments(source_of(path)), "statusTextFromState"))
            self.assertIn(
                "describeArrivalWindowClause = describeArrivalWindow", status,
                "%s's status line does not build the arrival window clause "
                "from the rule, so a case cannot execute what an operator "
                "reads" % app)
            self.assertTrue(
                re.search(r"\[[^]\[]*describeArrivalWindowClause[^]\[]*\]",
                          status),
                "%s builds the arrival window clause and prints it nowhere, "
                "so a run still cannot say which way the feature is inert"
                % app)


class TheTwoAppsCarryTheSameRules(unittest.TestCase):
    """The four declarations, compared byte for byte across both apps.

    Nothing in these rules is app-specific -- they are arithmetic over a reading
    count and a list -- so a copy that drifts is a bug in whichever one drifted,
    and the drift is silent: both still compile, both still answer, and only one
    is the rule that was argued for. The doc comments are compared with the code
    for the same reason, since the argument for the unit and its cost is most of
    what a later reader has.

    The mission runner is deliberately absent from `APPS`: it carries neither
    `otherPilotsFoundOnArrival` nor a probe scanner to be late naming an
    anomaly, and a case asserts that rather than leaving it to be assumed.
    """

    def declaration(self, path, name):
        match = re.search(
            r"(\{-\|(?:(?!-\})[\s\S])*?-\}\n)?%s :[\s\S]*?(?=\n\n\n)"
            % re.escape(name), source_of(path))
        self.assertTrue(match, "no declaration named %r in %s" % (name, path))
        return match.group(0)

    def test_every_shared_rule_is_identical_in_both_apps(self):
        for name in SHARED_DECLARATIONS:
            copies = {app: self.declaration(path, name) for app, path in APPS}
            first = sorted(copies)[0]
            for app, text in copies.items():
                self.assertEqual(
                    text, copies[first],
                    "%s's %s has drifted from %s's -- both compile and both "
                    "answer, so the drift is silent" % (app, name, first))

    def test_the_mission_runner_carries_none_of_this(self):
        """Out of scope, asserted rather than assumed.

        If it ever grows an arrival snapshot it takes on this bug with it, and
        this case is what makes somebody notice.
        """
        mission_runner = os.path.join(
            REPO_DIR, "implement", "applications", "eve-online",
            "eve-online-mission-runner", "Bot.elm")
        self.assertNotIn(
            "otherPilotsFoundOnArrival", source_of(mission_runner),
            "the mission runner has grown an arrival snapshot, which means it "
            "has taken on #194 as well and is no longer out of scope")


if __name__ == "__main__":
    unittest.main()
