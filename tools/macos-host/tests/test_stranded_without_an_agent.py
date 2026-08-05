"""Tests for leaving a station that has no agent, instead of asking for help.

Issue #127. Run 35 printed

    +++ I do not see an agent to talk to in this station.
    ++++ I am stuck here and need help to continue.

on **371 readings**, and on every one of them the status line said
`Home station: 'Amarr VIII (Oris) - Emperor Family Academy' (... docked
elsewhere)`. The bot knew a station with an agent in it, knew it was not
standing in that station, and asked a person to come and fix it instead.

**The issue's own first question is answered against it, and the answer changes
what the fix has to be.** Why the bot was docked in a foreign station was
unverified and suspected of being the real defect. It is not: run 35's mission
was the courier `The Heir's Favorite Slave -- Bring Slaves to Ashokon Bofazan`,
the mission tracker's own travel steps flew it to Bofazan's station, and it
handed the mission in there through the conversation the tracker opened. The
docking was correct and the mission completed. What follows the hand-in is the
gap: the bot asks the station it happens to be standing in for the next mission
and, finding nobody, has nothing else to try.

**The issue's arithmetic does not survive either, and the correction is in the
unit this repo keeps a section on.** "roughly 12,800 readings" is the *line*
count of the span, 32,528 to 45,303. The span is **1,064 readings over 304
framework steps and 383 seconds** -- six and a half minutes, not the hours the
reading count implies. `readings_in_span` below pins that, because a fix sized
against the wrong number is sized against nothing.

**What ended the stall was a person, and the log says so obliquely.** For the
284 readings before it the bot dispatched no input at all -- the help branch
clicks nothing -- and then an agent conversation window appears in one reading
with `Seek and Destroy` in it. The framework's next dispatch after that carries
`standing down: someone used the mouse/keyboard 1.5s ago`. The same thing
happened at the first station: the ship undocked without the bot ever deciding
to, and the bot then flew six jumps on the route it found set and docked at
`Bhizheba IX - Moon 1 - Amarr Navy Logistic Support` unaided. That second half
is the one piece of the fix that needed no writing, and `TheFlightHalfIsAlreadyThere`
is where it is pinned.

**Whether the station really had no agent is still not known**, and this change
does not claim to have found out. `describeNoAgentToTalkTo` exists so that the
next occurrence can be read: the bare sentence could not distinguish an empty
panel from a populated one every row of which `selectedAgentEntry` rejected, and
those want opposite fixes.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH with the app's dependencies fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The run the issue is about.
THE_INCIDENT = "35"

# What run 35 printed, and how often.
NO_AGENT_LINE = "I do not see an agent to talk to in this station."
NO_AGENT_READINGS = 371
# Every one of them, so the fix's precondition held on all of them: a home
# station is configured and the info panel could say this is not it.
DOCKED_ELSEWHERE = "docked elsewhere"

# The span, in the unit the issue got wrong. 1,064 readings, not 12,800.
READINGS_IN_SPAN = 1064

# The station the bot flew to unaided once a person had undocked it, which is
# the half of the trip this change does not have to write.
STATION_IT_REACHED = "Bhizheba IX - Moon 1 - Amarr Navy Logistic Support"
TRAVEL_THE_ROUTE_LINE = "A route is set -- travel towards the mission's system."


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case.

    #58's reformatting broke three assertions written against exact
    indentation; every source-reading case here goes through this, and the
    expected strings are written the same way.
    """
    return " ".join(text.split())


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case below that asserts a branch is *absent* needs this: `collapsed`
    puts a comment on the same line as the code, and the comments here name the
    branches deliberately left elsewhere.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(source, name):
    """One top-level declaration, from its type annotation to the next gap."""
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return rest[:rest.index("\n\n\n")]


def int_constant(name):
    """A constant read out of `Bot.elm`, so a case tests the shipped number
    rather than one restated here."""
    body = declaration(bot_source(), name)
    return int(re.search(r"\n%s =\s*(\d+)" % name, "\n" + body).group(1))


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def elm_maybe_string(value):
    return "Nothing" if value is None else "(Just %s)" % elm_string(value)


def readings(path):
    """Every reading in a log, as its own block of lines.

    One `RequestToVolatileProcess` memory read per reading is the per-reading
    identity #142 established; the `# [N.M]` header is what delimits them here,
    and `N` is a framework step spanning several readings rather than a reading
    itself. Counting in the wrong one of those is what produced the issue's
    "12,800".

    **The framework's own `#` notes come before the header of the reading they
    belong to**, not after it, so they are buffered and attached forwards.
    `standing down: someone used the mouse/keyboard` is one of them and it is
    the only trace a person at the keyboard leaves in this log.

    The header's own trailing text -- the mission line, or `No mission
    running.` -- is kept as a line of the reading, because half of what a case
    here asks about is in it.
    """
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    blocks = []
    current = None
    pending = []
    for line in text.split("\n"):
        header = re.match(r"# \[(\d+)\.(\d+)\] \(([\d.]+)s\) ?(.*)", line)
        if header:
            if current is not None:
                blocks.append(current)
            current = {"step": int(header.group(1)),
                       "reading": int(header.group(2)),
                       "seconds": float(header.group(3)),
                       "lines": pending + [header.group(4)]}
            pending = []
        elif current is not None:
            if line.startswith("--------"):
                blocks.append(current)
                current = None
            else:
                current["lines"].append(line)
        else:
            pending.append(line)
    if current is not None:
        blocks.append(current)
    return blocks


def said_in(reading, text):
    return any(text in line for line in reading["lines"])


class WhereAStrandedBotGoes(unittest.TestCase):
    """`agentStationTrip`, executed, at every boundary it has.

    A pure rule over a record rather than a shape read out of the source,
    because each of its three tests refuses the trip for a different reason and
    a case has to be able to reach all of them. The one that matters most is the
    middle one: `stationsKnownToHaveAnAgent` leads with
    `lastDockedStationNameFromInfoPanel`, which while docked names the station
    the ship is standing in, so a rule that did not drop it would route the ship
    to its own hangar and undock for nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-stranded-trip-")
        cls.trip_seconds = int_constant("strandedAgentTripSeconds")
        cls.wind_down = int_constant("secondsBeforeSessionEndToWindDown")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _trip(self, candidates, docked, seconds_left):
        return (
            "agentStationTrip { candidateStations = [ %s ]"
            ", dockedStationName = %s"
            ", secondsToSessionEnd = %s"
            ", secondsBeforeWindDown = %d"
            ", tripSecondsNeeded = %d }"
            % (", ".join(elm_string(name) for name in candidates),
               elm_maybe_string(docked),
               "Nothing" if seconds_left is None else "(Just %d)" % seconds_left,
               self.wind_down, self.trip_seconds))

    def _travels_to(self, candidates, docked, seconds_left, station):
        return "%s == TravelToAgentStation %s" % (
            self._trip(candidates, docked, seconds_left), elm_string(station))

    def _refuses(self, candidates, docked, seconds_left):
        return "%s /= TravelToAgentStation %s" % (
            self._trip(candidates, docked, seconds_left),
            elm_string(candidates[0] if candidates else ""))

    def test_it_skips_the_station_it_is_standing_in(self):
        # The whole point. The first candidate is where run 35 was docked; the
        # trip has to be to the second.
        self.assertEqual(
            self.repl.evaluate([
                self._travels_to(["Penirgman VII", "Amarr VIII (Oris)"],
                                 "Penirgman VII", 5000, "Amarr VIII (Oris)")]),
            [True])

    def test_it_goes_to_the_first_candidate_when_that_is_not_here(self):
        # Order is preference: the station we last undocked from is the agent's
        # own, and it wins over `home-station` when the two differ.
        self.assertEqual(
            self.repl.evaluate([
                self._travels_to(["The Agent's", "Home"], "Somewhere Else",
                                 5000, "The Agent's")]),
            [True])

    def test_it_will_not_undock_without_knowing_where_it_is(self):
        # `goToHomeStationWhileDocked`'s rule, for its reason: undocking towards
        # a station we may already be standing in costs the session.
        self.assertEqual(
            self.repl.evaluate([self._refuses(["Home"], None, 5000)]),
            [True])

    def test_it_refuses_when_every_station_it_knows_is_this_one(self):
        self.assertEqual(
            self.repl.evaluate([self._refuses(["Home"], "Home", 5000)]),
            [True])

    def test_it_refuses_when_it_knows_of_no_station_at_all(self):
        answers = self.repl.evaluate([
            "%s == NoTripToAnAgentStation %s" % (
                self._trip([], "Anywhere", 5000),
                elm_string(
                    "I know of no station with an agent in it: no "
                    "'home-station' is configured and I have not undocked from "
                    "anywhere this session")),
        ])
        self.assertEqual(answers, [True],
                         "a bot with nowhere to go has to say that, and not "
                         "blame the clock for it")

    def test_the_clock_bound_is_the_wind_down_plus_the_trip(self):
        # Both sides of the boundary, because a comparison moved by one is the
        # mutation this case exists to catch. The trip has to fit *before* the
        # wind-down starts, not before the session ends -- the wind-down sits
        # above this branch and takes the tree back at that point.
        just_enough = self.wind_down + self.trip_seconds
        answers = self.repl.evaluate([
            self._travels_to(["A", "B"], "A", just_enough, "B"),
            self._travels_to(["A", "B"], "A", just_enough - 1, "B"),
        ])
        self.assertEqual(answers, [True, False])

    def test_no_session_deadline_means_no_bound_to_fit_inside(self):
        # The host was given no `--session-duration-minutes`, which is the same
        # thing `windDownBeforeSessionEnd` concludes from a `Nothing` here.
        self.assertEqual(
            self.repl.evaluate([self._travels_to(["A", "B"], "A", None, "B")]),
            [True])

    def test_having_nowhere_to_go_is_decided_before_the_clock(self):
        # Order of the tests is the order of what the bot can know, and a bot
        # with nowhere to go that blamed the session clock would send an
        # operator looking at the wrong thing.
        answers = self.repl.evaluate([
            "%s == NoTripToAnAgentStation %s" % (
                self._trip(["Home"], "Home", 0),
                elm_string("every station I know of with an agent in it is "
                           "the one I am already docked at")),
        ])
        self.assertEqual(answers, [True])

    def test_a_control_row_rides_along(self):
        # So a repl answering `True` to everything cannot pass the cases above.
        answers = self.repl.evaluate([
            self._travels_to(["A", "B"], "A", 5000, "B"),
            self._travels_to(["A", "B"], "A", 5000, "A"),
        ])
        self.assertEqual(answers, [True, False])


class TheStationNameIsMatchedInOneDirection(unittest.TestCase):
    """`stationNameMatches`, executed.

    Split out of `dockedAtHomeStation` so that both questions -- "am I home?"
    and "is this candidate the station I am standing in?" -- are one rule.
    Two would be two things that can disagree, and the disagreement undocks a
    ship for nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-stranded-names-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _matches(self, panel, wanted):
        return "stationNameMatches { fromInfoPanel = %s, wanted = %s }" % (
            elm_string(panel), elm_string(wanted))

    def test_it_matches_the_same_name(self):
        home = "Amarr VIII (Oris) - Emperor Family Academy"
        self.assertEqual(self.repl.evaluate([self._matches(home, home)]), [True])

    def test_it_ignores_case_and_surrounding_space(self):
        answers = self.repl.evaluate([
            self._matches("  Amarr VIII (Oris) ", "amarr viii (oris)"),
        ])
        self.assertEqual(answers, [True])

    def test_the_panel_may_decorate_the_configured_name(self):
        self.assertEqual(
            self.repl.evaluate([
                self._matches("Amarr VIII (Oris) - Emperor Family Academy",
                              "Emperor Family Academy")]),
            [True])

    def test_a_short_configured_name_does_not_match_the_constellation(self):
        # Containment only in that direction. A candidate of "Amarr" matching
        # every station in the constellation would silently make the trip a
        # no-op wherever the ship happened to be.
        self.assertEqual(
            self.repl.evaluate([
                self._matches("Amarr", "Amarr VIII (Oris) - Emperor Family Academy")]),
            [False])

    def test_two_different_stations_do_not_match(self):
        self.assertEqual(
            self.repl.evaluate([
                self._matches("Bhizheba IX - Moon 1 - Amarr Navy Logistic Support",
                              "Amarr VIII (Oris) - Emperor Family Academy")]),
            [False])


class TheAlarmSaysWhatTheTabActuallyHeld(unittest.TestCase):
    """`describeNoAgentToTalkTo`, executed.

    The issue's second unverified question is whether the station really had no
    agent or whether the parse missed one, and it notes that the log cannot
    distinguish them and that they want opposite fixes. It still cannot -- run
    35 is over -- so what this line is for is making the next one answerable.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-stranded-alarm-")
        cls.empty, cls.populated = cls.repl.strings([
            "describeNoAgentToTalkTo []",
            'describeNoAgentToTalkTo [ "Fisten Akulf, Security, here, not available"'
            ', "Ashokon Bofazan, Storyline - Security, Penirgman, available" ]',
        ])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_keep_the_sentence_the_issue_quotes(self):
        self.assertIn(NO_AGENT_LINE, self.empty)
        self.assertIn(NO_AGENT_LINE, self.populated)

    def test_an_empty_tab_says_it_could_be_a_parse_failure(self):
        # The half the operator cannot see from outside: "no agents here" and
        # "the panel did not parse" produce the same silence.
        self.assertIn("lists nobody at all", self.empty)
        self.assertIn("did not parse", self.empty)

    def test_a_populated_tab_names_every_row_it_rejected(self):
        # Both recorded shapes of a rejected row appear here, and both really
        # occur: runs 18 and 19 list `Fisten Akulf, Security, here, not
        # available` in the same panel as an agent the bot could use.
        self.assertIn("Fisten Akulf, Security, here, not available",
                      self.populated)
        self.assertIn("Ashokon Bofazan, Storyline - Security, Penirgman, available",
                      self.populated)

    def test_a_populated_tab_says_how_many_and_why_none_of_them_served(self):
        self.assertIn("2", self.populated)
        self.assertIn("available and in this station", self.populated)

    def test_the_two_readings_are_distinguishable(self):
        self.assertNotEqual(self.empty, self.populated)

    def test_it_carries_no_per_reading_counter(self):
        # `stall_watch.py` dedupes on the whole line, and run 126 emitted 151
        # unique variants of one alarm by putting a counter in it. The panel
        # does not change while the ship is docked, so this is one line however
        # long the state lasts.
        for varying in ["reading", "readings", "consecutive", "so far"]:
            self.assertNotIn(varying, self.empty)
            self.assertNotIn(varying, self.populated)


class TheTripIsOnlyOfferedInTheStrandedState(unittest.TestCase):
    """Where the new branch is asked, and where it deliberately is not.

    `openAgentConversation` has four failure branches and three other callers.
    Only one branch is evidence about the *station* and only one caller is the
    one #127 is about, so the trip is offered at exactly that intersection --
    anywhere else and a bot holding a finished mission would fly away from the
    agent it has to hand it to.
    """

    def setUp(self):
        self.source = bot_source()

    def _declaration(self, name):
        return collapsed(without_comments(declaration(self.source, name)))

    def test_the_no_mission_caller_is_the_one_that_offers_a_trip(self):
        body = self._declaration("decideActionWhenDockedWithMissionTracker")
        self.assertIn("No mission running -- get one from the agent.", body)
        self.assertIn("travelToAnAgentWhenThisStationHasNone context", body)

    def test_the_other_callers_still_only_open_the_conversation(self):
        # Handing a finished mission in and giving one back both have to happen
        # face to face with the agent whose mission it is. Travelling away from
        # that station is the opposite of what either wants.
        for caller in ["decideActionWhenDockedWithMissionTracker",
                       "abandonMissionThatCannotProgress"]:
            body = self._declaration(caller)
            for phrase in ["The mission is done -- talk to the agent to hand it in.",
                           "Docked -- open the agent conversation"]:
                if phrase in body:
                    around = body[body.index(phrase):body.index(phrase) + 300]
                    self.assertNotIn(
                        "travelToAnAgentWhenThisStationHasNone", around,
                        "%s must not fly away from the agent it needs" % phrase)

    def test_the_trip_is_offered_from_exactly_one_place(self):
        asked_in = [name for name in
                    ["decideActionWhenDockedWithMissionTracker",
                     "decideActionWhenDockedWithoutConversation",
                     "openAgentConversation",
                     "abandonMissionThatCannotProgress",
                     "windDownBeforeSessionEnd"]
                    if "travelToAnAgentWhenThisStationHasNone"
                    in self._declaration(name)]
        self.assertEqual(asked_in, ["decideActionWhenDockedWithMissionTracker"])

    def test_only_a_selected_tab_with_no_row_counts_as_stranded(self):
        # An unread panel is not evidence that the station has no agent. A tab
        # that is not selected has a click still to come, and run 35 spent 242
        # readings on exactly that click.
        body = self._declaration("thisStationHasNoAgentForUs")
        self.assertIn("agentsTab.isSelected", body)
        self.assertIn("selectedAgentEntry context", body)
        self.assertNotIn("clickUiElement", body)

    def test_asking_for_help_is_still_the_answer_with_nowhere_to_go(self):
        body = self._declaration("travelToAnAgentWhenThisStationHasNone")
        self.assertIn("NoTripToAnAgentStation reason", body)
        self.assertIn("openAgentConversation context", body)

    def test_the_ship_only_undocks_once_the_route_is_set(self):
        # `goToHomeStationWhileDocked`'s order, for its reason: setting a
        # destination is the step that can fail, and failing it while still
        # docked costs nothing. So the undock is the *then* of the route test
        # and setting the route is the *else*, never the other way round.
        body = self._declaration("travelToAnAgentWhenThisStationHasNone")
        self.assertIn("if homeStationRouteIsSet context stationName then", body,
                      "the undock has to be the *then* of the route test, so "
                      "an inverted or absent guard is a failure here rather "
                      "than an error in this case")
        guard = body.index("if homeStationRouteIsSet context stationName then")
        undock = body.index("undockUsingStationWindow context")
        route = body.index("routeToStation context stationName")
        self.assertLess(guard, undock,
                        "a ship that undocks before the route is set is in "
                        "space with nowhere to go")
        self.assertLess(undock, route)
        self.assertIn("else", body[undock:route])

    def test_the_two_known_stations_are_one_list(self):
        # `stationToReturnToForAbandonment` and the trip choose from the same
        # two places, and the issue names both. Two lists would be two things
        # that could disagree about where an agent is.
        body = self._declaration("stationToReturnToForAbandonment")
        self.assertIn("stationsKnownToHaveAnAgent context", body)
        known = self._declaration("stationsKnownToHaveAnAgent")
        self.assertIn("context.memory.lastDockedStationNameFromInfoPanel", known)
        self.assertIn("context.eventContext.botSettings.homeStationName", known)

    def test_the_trip_budget_is_a_named_constant(self):
        self.assertGreater(int_constant("strandedAgentTripSeconds"), 0)
        body = self._declaration("travelToAnAgentWhenThisStationHasNone")
        self.assertIn("tripSecondsNeeded = strandedAgentTripSeconds", body)
        self.assertIn("secondsBeforeWindDown = secondsBeforeSessionEndToWindDown",
                      body)


class WhatRunThirtyFiveActuallyDid(unittest.TestCase):
    """The corpus, on the three things #127 left unverified."""

    @classmethod
    def setUpClass(cls):
        cls.runs = dict(recorded_runs(THE_INCIDENT))
        cls.readings = readings(cls.runs[THE_INCIDENT])
        cls.stranded = [reading for reading in cls.readings
                        if said_in(reading, NO_AGENT_LINE)]

    def test_the_help_alarm_was_raised_on_every_stranded_reading(self):
        self.assertEqual(len(self.stranded), NO_AGENT_READINGS)
        self.assertTrue(
            all(said_in(reading, "I am stuck here and need help to continue.")
                for reading in self.stranded))

    def test_a_home_station_was_configured_on_all_of_them(self):
        # The fix's precondition. Nothing here is a case about a state the bot
        # was never in.
        self.assertTrue(
            all(said_in(reading, "Home station: 'Amarr VIII (Oris)")
                for reading in self.stranded))

    def test_the_info_panel_could_say_this_was_not_that_station(self):
        # `describeHomeStation` prints ", docked elsewhere" only for
        # `dockedAtHomeStation == Just False`, which needs
        # `dockedStationNameFromInfoPanel` to have answered. So
        # `agentStationTrip` would have had a `Just` to work from on every one
        # of these readings, and would have flown.
        self.assertTrue(
            all(said_in(reading, DOCKED_ELSEWHERE) for reading in self.stranded))

    def test_the_span_is_counted_in_readings_and_not_in_lines(self):
        # The issue's "roughly 12,800 readings" is the line count. 1,064
        # readings over 304 framework steps -- `[N.M]`, where N is a step
        # spanning several readings -- and 383 seconds of them.
        first = self.readings.index(self.stranded[0])
        last = self.readings.index(self.stranded[-1])
        span = self.readings[first:last + 1]
        self.assertEqual(len(span), READINGS_IN_SPAN)
        steps = {reading["step"] for reading in span}
        self.assertLess(len(steps), len(span) // 3,
                        "a step spans several readings, which is why counting "
                        "in the wrong one produces an order-of-magnitude error")
        seconds = sum(reading["seconds"] for reading in span
                      if reading["reading"] == 0)
        self.assertLess(seconds, 600)

    def test_the_docking_was_the_mission_tracker_leading_it_there(self):
        # #127's first unverified question, answered against the issue: the
        # docking is not the defect. The courier mission's own delivery step
        # is what put the bot in a station whose agent list it could not use.
        before = self.readings[:self.readings.index(self.stranded[0])]
        self.assertTrue(
            any(said_in(reading, "Bring") and said_in(reading, "Ashokon Bofazan")
                for reading in before),
            "run 35's mission was the courier that took it there")
        self.assertTrue(
            any(said_in(reading, "The mission tracker offers the next travel step: 'Dock'")
                for reading in before),
            "and the tracker's own travel step is what docked it")
        self.assertTrue(
            any(said_in(reading, "Hand the finished mission in.")
                for reading in before),
            "and the mission was handed in there, so the trip was not wasted")

    def test_the_panel_path_never_once_succeeded_in_this_run(self):
        # Not a single "Start a conversation with" in 26,487 readings. Whatever
        # the panel held, `selectedAgentEntry` never chose a row from it.
        self.assertFalse(
            any(said_in(reading, "Start a conversation with")
                for reading in self.readings))


class TheFlightHalfIsAlreadyThere(unittest.TestCase):
    """Run 35 flew the trip this change decides to start.

    A person undocked the ship mid-stall. The bot, with no mission and a route
    already set, took `decideActionInMissionPocket`'s `travelTheRoute` branch,
    flew six gate jumps and docked at Bhizheba on its own -- 120 steps, 448
    readings, 190 seconds. So the only untested part of the fix is the two
    steps before the undock, which is what makes it a small change rather than
    a new travel path.
    """

    @classmethod
    def setUpClass(cls):
        cls.runs = dict(recorded_runs(THE_INCIDENT))
        cls.readings = readings(cls.runs[THE_INCIDENT])

    def test_it_travelled_a_standing_route_with_no_mission_running(self):
        travelling = [reading for reading in self.readings
                      if said_in(reading, TRAVEL_THE_ROUTE_LINE)
                      and said_in(reading, "No mission running.")]
        self.assertTrue(travelling,
                        "the in-space half of the trip is exercised in the "
                        "corpus, with no mission to lead it")

    def test_it_docked_at_the_far_end_without_being_told_to(self):
        self.assertTrue(
            any(said_in(reading, "Dock at %s" % STATION_IT_REACHED)
                for reading in self.readings))

    def test_a_person_was_at_the_keyboard_when_the_stall_broke(self):
        # What ended it, which #127 records as unexplained. The bot dispatched
        # no input for the whole stall -- the help branch clicks nothing -- and
        # the framework only logs a stand-down on a step that had effects to
        # send, so the note lands on the first dispatch after the conversation
        # appeared rather than before it.
        stranded = [index for index, reading in enumerate(self.readings)
                    if said_in(reading, NO_AGENT_LINE)]
        after = self.readings[stranded[-1]:stranded[-1] + 40]
        self.assertTrue(
            any(said_in(reading, "Accept the mission 'Seek and Destroy'")
                for reading in after),
            "an agent conversation appeared with no click of the bot's before it")
        self.assertTrue(
            any(said_in(reading, "someone used the mouse/keyboard")
                for reading in after),
            "and the framework's next dispatch says a person had just used the "
            "mouse")


if __name__ == "__main__":
    unittest.main()
