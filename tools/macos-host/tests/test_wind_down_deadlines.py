"""Tests for the three deadlines the wind-down gives a trip to the home station.

The trip added by #25 has three phases and each ends on a different clock. Until
this change two of those clocks were wrong, and both were wrong in the direction
that reads like success in the log.

**Phase 1, setting the route while still docked where the mission left us.**
`dockedWindDownDeadlineSeconds` returned a flat `0`, so the whole six-step search
bar cascade -- click the field, type, Return, expand `Stations (N)`,
double-click the row, click Set Destination -- had to fit inside
`secondsBeforeSessionEndToWindDown` (200 s) or the session ended with the ship
still in the wrong station. Every other leg of the wind-down had an overrun; this
one, the only leg that had never run live, had none.

**Phase 3, restocking once the ship is home.** The flight was allowed to run to
`-homeStationTripSecondsPastSessionEnd` (420 s) while the restock's deadline sat
at `-homeStationRestockGraceSeconds` (60 s), and the docked branch tests its
deadline *before* it reaches the restock. So a ship arriving any later than 60 s
past the planned end ended the session on the reading it docked -- a 360-second
window in which the trip completed perfectly and bought nothing at all. The
docstring on `homeStationRestockGraceSeconds` says the grace exists precisely
because "arriving and then finishing without restocking would waste the whole
trip", so the intent was right and only the anchor was wrong: measured from the
planned end, it could be outlived by the flight that had to happen first.

Both are now anchored to the trip rather than to the planned end, and phase 2 is
untouched.

**The numbers come from run 14**, the first run to fly this hull through five
missions with a home station configured. Its agent station (Amarr VI (Zorast) -
Moon 2 - Theology Council Tribunal) and its home station (Amarr VIII (Oris) -
Emperor Family Academy) are both in the Amarr system, so the trip is an
intra-system warp with no gate jumps. The same run measures that warp and dock
five times, as the gap between the tracker showing `(next step: Dock)` and the
hand-in conversation opening:

    The Blockade                    23 readings    65 s
    The Score                       20 readings    54 s
    Eliminate the Pirate Campers    21 readings    54 s
    Seek and Destroy                19 readings    49 s
    The Score (again)               20 readings    48 s

-- against which the 300 s this change reserves for the flight is about five
times the worst case. Readings on that run averaged 3.1 s (3,916 s over 1,261
ticks), so phase 1's new allowance of 200 + 120 s is roughly 100 readings for a
cascade that should take twenty-five.

**Why the reserve is the whole reason phase 1 has its own constant.** The
in-space branch ends the session at `-homeStationTripSecondsPastSessionEnd`
whatever the ship is doing. A preparation phase granted that same 420 s could
undock at 419 and be cut off one second later -- ending the session *in space*,
which is the outcome the trip's allowance exists to avoid. So the check below is
not that phase 1 has *an* allowance but that it has a strictly smaller one.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched, which is what
`compile_bot.sh` leaves behind; they skip only if the repl cannot run at all.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The worst intra-system warp-and-dock run 14 measured, in seconds. The flight
# reserve is checked against this rather than against a round number.
WORST_MEASURED_WARP_AND_DOCK_SECONDS = 65


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def function_body(source, name):
    """The text of a top-level function, up to the next top-level definition."""
    match = re.search(
        r"^%s :.*?\n%s\b.*?(?=\n\n\n)" % (re.escape(name), re.escape(name)),
        source, re.S | re.M)
    assert match, "could not find %s in Bot.elm" % name
    return match.group(0)


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version` to
    whatever this machine's elm reports, and build there -- never in the
    checked-in source. The one extra step is opening `module Bot exposing (...)`
    to `(..)`, since the repl can only call what the module exports.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-wind-down-")
        self.app = os.path.join(self.scratch, "app")
        shutil.copytree(MISSION_RUNNER_DIR, self.app)

        version = subprocess.run(
            ["elm", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
        elm_json = os.path.join(self.app, "elm.json")
        with open(elm_json, encoding="utf-8") as source:
            patched = source.read().replace(
                '"elm-version": "0.19.1"', '"elm-version": "%s"' % version)
        with open(elm_json, "w", encoding="utf-8") as target:
            target.write(patched)

        bot = os.path.join(self.app, "Bot.elm")
        with open(bot, encoding="utf-8") as handle:
            source = handle.read()
        opened = re.sub(r"module Bot exposing\s*\([^)]*\)",
                        "module Bot exposing (..)", source, count=1)
        assert opened != source, "could not open Bot.elm's exports"
        with open(bot, "w", encoding="utf-8") as handle:
            handle.write(opened)

    def evaluate(self, expressions):
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def ask(self, expressions):
        script = "import Bot exposing (..)\n" + "".join(
            expression + "\n" for expression in expressions)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        answers = [answer == "True"
                   for answer in re.findall(r"(True|False) : Bool", plain)]
        return answers, plain, result.stderr

    def works(self):
        """Whether the repl can evaluate anything at all here.

        Distinguishes an environment where `elm repl` cannot run from the bot
        answering wrongly. Only the first is a reason to skip: a suite that
        skipped on any failure would be a check that never fires.
        """
        answers, plain, stderr = self.ask(
            ["homeStationTripSecondsPastSessionEnd > 0"])
        return answers == [True], plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def elm_is_available():
    return shutil.which("elm") is not None


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheBudgetIsExecutedRatherThanMirrored(unittest.TestCase):
    """The constants answer for themselves, so a retune fails here."""

    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        works, output = cls.repl.works()
        if not works:
            cls.repl.close()
            raise unittest.SkipTest("elm repl cannot run here:\n%s" % output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_four_constants_hold_their_measured_values(self):
        self.assertEqual(
            [True, True, True, True],
            self.repl.evaluate([
                "secondsBeforeSessionEndToWindDown == 200",
                "homeStationRoutePreparationSecondsPastSessionEnd == 120",
                "homeStationTripSecondsPastSessionEnd == 420",
                "homeStationRestockGraceSeconds == 60",
            ]))

    def test_preparing_the_route_gets_less_than_the_flight_it_prepares(self):
        """Otherwise it can undock with no time left and end the run in space."""
        self.assertEqual([True], self.repl.evaluate([
            "homeStationRoutePreparationSecondsPastSessionEnd"
            " < homeStationTripSecondsPastSessionEnd",
        ]))

    def test_the_reserve_left_for_the_flight_covers_the_measured_worst_case(self):
        self.assertEqual([True], self.repl.evaluate([
            "(homeStationTripSecondsPastSessionEnd"
            " - homeStationRoutePreparationSecondsPastSessionEnd) >= %d"
            % (4 * WORST_MEASURED_WARP_AND_DOCK_SECONDS),
        ]))

    def test_the_flight_can_never_outlive_the_restock_grace(self):
        """The bug: a trip landing inside its own allowance found the docked
        deadline already passed. The grace is anchored past the trip, so every
        arrival the trip permits still has grace left."""
        self.assertEqual([True], self.repl.evaluate([
            "-(homeStationTripSecondsPastSessionEnd"
            " + homeStationRestockGraceSeconds)"
            " < -homeStationTripSecondsPastSessionEnd",
        ]))

    def test_preparation_still_starts_inside_the_wind_down(self):
        """The overrun is an extension of the window, not a replacement."""
        self.assertEqual([True, True], self.repl.evaluate([
            "secondsBeforeSessionEndToWindDown > 0",
            "homeStationRoutePreparationSecondsPastSessionEnd > 0",
        ]))


class TheDeadlineHasNoFlatZeroForAPendingTrip(unittest.TestCase):
    """Read out of the source, because the branch a context reaches is the
    property and building a whole `BotDecisionContext` in a repl is not worth
    what it would prove."""

    def setUp(self):
        self.body = function_body(bot_source(), "dockedWindDownDeadlineSeconds")

    def test_it_asks_whether_a_trip_is_pending_at_all(self):
        self.assertIn("case homeStationToGoTo context of", self.body)

    def test_no_trip_pending_still_ends_at_the_planned_end(self):
        self.assertRegex(self.body, r"Nothing ->\s*\n\s*0\b")

    def test_arriving_home_is_granted_the_trip_plus_the_grace(self):
        self.assertIn(
            "-(homeStationTripSecondsPastSessionEnd"
            " + homeStationRestockGraceSeconds)", self.body)

    def test_preparing_the_route_is_granted_its_own_allowance(self):
        self.assertIn(
            "-homeStationRoutePreparationSecondsPastSessionEnd", self.body)

    def test_the_only_zero_is_the_no_trip_case(self):
        """The regression in one line: a pending trip must not deadline at 0."""
        after_pending = self.body.split("Just stationName ->", 1)
        self.assertEqual(2, len(after_pending), self.body)
        self.assertNotRegex(after_pending[1], r"(?<![\d-])0\b")

    def test_the_caller_compares_against_it_rather_than_a_literal(self):
        source = bot_source()
        self.assertIn(
            "if secondsRemaining <= dockedWindDownDeadlineSeconds context then",
            source)


class TheRestockWindowCannotDriftFromTheWindDown(unittest.TestCase):
    """`withinDroneRestockWindow` and the docked wind-down have to agree: if the
    restock window closes first the bot sits docked doing nothing until the
    session ends, and if it closes last the session ends mid-restock. They used
    to agree by both naming `homeStationRestockGraceSeconds`, held together by a
    comment -- which is exactly what did not survive changing one of them."""

    def setUp(self):
        self.body = function_body(bot_source(), "withinDroneRestockWindow")

    def test_it_asks_the_wind_down_for_the_deadline(self):
        self.assertIn("dockedWindDownDeadlineSeconds context", self.body)

    def test_it_does_not_restate_the_grace(self):
        self.assertNotIn("-homeStationRestockGraceSeconds", self.body)

    def test_it_still_guards_on_the_same_condition(self):
        """The two agree by construction only because this is the very condition
        under which the deadline function returns the at-home value."""
        self.assertIn("homeStationRestockGraceApplies context", self.body)
        applies = function_body(bot_source(), "homeStationRestockGraceApplies")
        self.assertIn("homeStationToGoTo context", applies)
        self.assertIn("dockedAtHomeStation context stationName == Just True",
                      applies)
        deadline = function_body(bot_source(), "dockedWindDownDeadlineSeconds")
        self.assertIn("dockedAtHomeStation context stationName == Just True",
                      deadline)

    def test_the_ordinary_window_is_untouched(self):
        self.assertIn("droneRestockGiveUpSecondsBeforeSessionEnd", self.body)


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheOutcomesThatUsedToBeWrong(unittest.TestCase):
    """The caller's comparison is `secondsRemaining <= deadline -> finish`,
    asserted textually above. These replay it against the real constants for the
    two arrivals that used to end a session with the trip wasted."""

    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        works, output = cls.repl.works()
        if not works:
            cls.repl.close()
            raise unittest.SkipTest("elm repl cannot run here:\n%s" % output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_ship_home_100_seconds_late_still_restocks(self):
        """Old deadline -60 ended the session on the reading it docked."""
        self.assertEqual([True], self.repl.evaluate([
            "-100 > -(homeStationTripSecondsPastSessionEnd"
            " + homeStationRestockGraceSeconds)",
        ]))

    def test_a_ship_home_at_the_last_moment_the_flight_allowed_still_restocks(self):
        self.assertEqual([True], self.repl.evaluate([
            "-homeStationTripSecondsPastSessionEnd"
            " > -(homeStationTripSecondsPastSessionEnd"
            " + homeStationRestockGraceSeconds)",
        ]))

    def test_a_route_still_being_set_30_seconds_late_has_not_given_up(self):
        """Old deadline 0 ended the session before it ever undocked."""
        self.assertEqual([True], self.repl.evaluate([
            "-30 > -homeStationRoutePreparationSecondsPastSessionEnd",
        ]))

    def test_the_preparation_still_ends_eventually(self):
        """A longer bound, not a missing one -- issues #7 and #14."""
        self.assertEqual([True], self.repl.evaluate([
            "-500 <= -homeStationRoutePreparationSecondsPastSessionEnd",
        ]))


if __name__ == "__main__":
    unittest.main()
