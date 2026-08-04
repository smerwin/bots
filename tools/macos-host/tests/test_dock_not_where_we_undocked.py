"""Tests for the mission runner declining to dock back into the station it
just undocked from.

Issue #98, a regression from #94. `dockAtDestinationStation` picks the *nearest*
station off the overview and presses the Selected Item panel's Dock button on it.
Its own doc comment named the hazard -- "nothing in that pick says the station is
the route's destination" -- and answered it with a route-marker count: one marker
means the destination is in this system, so the nearest station was taken to be
it.

One marker does not mean that. It means the destination is in this system and
says nothing about the destination being a station, let alone which one. Run 28's
mission wanted the ship in Sarum Prime; the ship was already there and already
docked at `Sarum Prime III - Moon 2 - Imperial Academy`. So the marker count was
1, the nearest station was the one at 0 m the ship had just left, its Dock button
was necessarily offered, and the bot docked straight back in -- **498 times**,
against a tracker whose own next step was `Undock`.

**Why the tracker's step is not the guard.** The issue proposed refusing to dock
while the tracker reads `Undock` or `Abort Undock`, and said that alone would
have prevented it. Bucketing every one of the run's zero-metre docks by the step
on the *same* reading says otherwise:

    Destination Set   357        Undock / Abort Undock   0

The `Undock` steps are real -- 221 of them -- but they land on *docked* readings,
where the bot correctly clicks Undock. The dock decision happens on the next
reading, in space, where the tracker reads `Destination Set`. The two never
coincide, so a guard keyed on the step never fires.

**Why distance is not the guard either**, which the issue got right: 0 m reads
the same on the way out as on the way in, so a floor cannot separate "just
undocked from" and "just arrived at".

What is left is identity plus a latch, which is what these cases execute:
`undockedFromStationAfterReading` carries the name of the station being left from
the one reading that can name it, and drops it once the ship warps.
`stationNameIsTheOneUndockedFrom` compares that name against the overview row.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The station run 28 undocked from and docked back into, as the info panel and
# the overview each wrote it.
STATION_LEFT = "Sarum Prime III - Moon 2 - Imperial Academy"

# The agent station the same session called home, and a stand-in for any station
# that is not the one just left. Docking here must stay available.
ANOTHER_STATION = "Amarr VIII (Oris) - Emperor Family Academy"


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def elm_maybe_string(value):
    return "Nothing" if value is None else "(Just %s)" % elm_string(value)


def latch_expression(docked_now, docked_in_last_reading, warping_now,
                     last_docked_station_name, before):
    warping = {None: "Nothing", True: "(Just True)", False: "(Just False)"}
    return (
        "undockedFromStationAfterReading "
        "{ dockedNow = %s, dockedInLastReading = %s, warpingNow = %s, "
        "lastDockedStationName = %s, before = %s }"
        % ("True" if docked_now else "False",
           "True" if docked_in_last_reading else "False",
           warping[warping_now],
           elm_maybe_string(last_docked_station_name),
           elm_maybe_string(before)))


class TheLatchFollowsTheShip(unittest.TestCase):
    """`undockedFromStationAfterReading`, over the states a trip passes through."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-undocked-from-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_undock_is_what_arms_it(self):
        # The one reading that can name the station being left: not docked now,
        # docked in the last reading. Any later reading has lost the name.
        armed = latch_expression(
            docked_now=False, docked_in_last_reading=True, warping_now=False,
            last_docked_station_name=STATION_LEFT, before=None)
        self.assertEqual(
            self.repl.evaluate(["%s == Just %s" % (armed, elm_string(STATION_LEFT))]),
            [True])

    def test_it_is_carried_while_the_ship_sits_in_the_undock(self):
        # The readings run 28 spent docking back in. Nothing here says the ship
        # left, so the latch has to survive them -- one that cleared itself
        # after a reading would let the loop straight back in.
        held = latch_expression(
            docked_now=False, docked_in_last_reading=False, warping_now=False,
            last_docked_station_name=STATION_LEFT, before=STATION_LEFT)
        self.assertEqual(
            self.repl.evaluate(["%s == Just %s" % (held, elm_string(STATION_LEFT))]),
            [True])

    def test_the_warp_clears_it(self):
        # The ship is demonstrably somewhere else. Leaving it armed past this
        # would refuse the dock at the far end of the trip, which is the whole
        # journey wasted rather than one reading.
        warped = latch_expression(
            docked_now=False, docked_in_last_reading=False, warping_now=True,
            last_docked_station_name=STATION_LEFT, before=STATION_LEFT)
        self.assertEqual(self.repl.evaluate(["%s == Nothing" % warped]), [True])

    def test_docking_clears_it(self):
        # Docked anywhere, the latch is spent: whatever the ship does next
        # starts from where it now is.
        docked = latch_expression(
            docked_now=True, docked_in_last_reading=False, warping_now=False,
            last_docked_station_name=STATION_LEFT, before=STATION_LEFT)
        self.assertEqual(self.repl.evaluate(["%s == Nothing" % docked]), [True])

    def test_an_unnamed_station_arms_nothing(self):
        # A reading whose info panel never named the station cannot arm the
        # guard. That direction leaves the dock available, which is the safe
        # one: refusing to dock on a name nobody read strands a ship that has
        # arrived.
        unnamed = latch_expression(
            docked_now=False, docked_in_last_reading=True, warping_now=False,
            last_docked_station_name=None, before=None)
        self.assertEqual(self.repl.evaluate(["%s == Nothing" % unnamed]), [True])


class TheStationIsComparedByName(unittest.TestCase):
    """`stationNameIsTheOneUndockedFrom`, over the names the two windows write."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-undocked-name-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _asked(self, undocked_from, overview_name):
        return "stationNameIsTheOneUndockedFrom %s %s" % (
            elm_maybe_string(undocked_from), elm_maybe_string(overview_name))

    def test_run_28_s_own_pair_matches(self):
        # The case that is the issue: the latched name and the overview row are
        # the same station, so the dock is declined.
        self.assertEqual(
            self.repl.evaluate([self._asked(STATION_LEFT, STATION_LEFT)]),
            [True])

    def test_a_different_station_does_not_match(self):
        # The trip's far end, and the reason this is a name test rather than a
        # distance one. A station that is not the one just left must stay
        # dockable, or #94 buys nothing.
        self.assertEqual(
            self.repl.evaluate([self._asked(STATION_LEFT, ANOTHER_STATION)]),
            [False])

    def test_the_two_windows_need_not_write_it_identically(self):
        # `dockedAtHomeStation`'s reason, and the same tolerance: the latch
        # carries the info panel's `currentStationName` and the row carries the
        # overview's `objectName`, and nothing guarantees the spacing or case
        # agree. A control rides along so a repl answering `True` to everything
        # cannot pass this.
        answers = self.repl.evaluate([
            self._asked(STATION_LEFT, "  " + STATION_LEFT + "  "),
            self._asked(STATION_LEFT, STATION_LEFT.lower()),
            self._asked(STATION_LEFT, STATION_LEFT.upper()),
            self._asked(STATION_LEFT, ANOTHER_STATION),
        ])
        self.assertEqual(answers, [True, True, True, False])

    def test_an_unread_name_on_either_side_declines_to_block(self):
        # Both directions of "this reading cannot say". The answer is `False`
        # either way -- the guard only ever blocks on a name it actually read.
        answers = self.repl.evaluate([
            self._asked(None, STATION_LEFT),
            self._asked(STATION_LEFT, None),
            self._asked(None, None),
        ])
        self.assertEqual(answers, [False, False, False])


class TheGuardIsWiredIntoTheDock(unittest.TestCase):
    """That the rule above is what `dockAtDestinationStation` consults.

    A rule no branch asks is a rule that cannot prevent anything, which is the
    shape #98 arrived in: the hazard was written down in a doc comment and never
    executed.
    """

    def setUp(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
            self.source = source.read()

    def _declaration(self, name):
        start = self.source.index("\n%s :" % name)
        rest = self.source[start + 1:]
        end = rest.index("\n\n\n")
        return rest[:end]

    def test_the_dock_branch_asks_the_guard(self):
        self.assertIn("stationIsTheOneJustUndockedFrom context station",
                      self._declaration("dockAtDestinationStation"))

    def test_the_guard_reads_the_latch(self):
        self.assertIn("context.memory.undockedFromStation",
                      self._declaration("stationIsTheOneJustUndockedFrom"))

    def test_a_declined_dock_falls_through_to_the_cascade(self):
        # Not a wait. The cascade is the pre-#94 mechanism and it still travels
        # the route, so declining the panel costs the optimisation rather than
        # the trip.
        declaration = self._declaration("dockAtDestinationStation")
        guard_at = declaration.index("stationIsTheOneJustUndockedFrom")
        self.assertIn("ifThePanelCannotDoIt", declaration[guard_at:])


if __name__ == "__main__":
    unittest.main()
