"""Tests for the bot asking the host to set its route through ESI.

`esi_waypoint.py` has worked since #23 and nothing had ever used it, because
`OperateBotConfiguration` gives a running bot one way out --
`buildTaskFromEffectSequence` -- and its vocabulary is mouse moves, buttons,
keys and scroll. A station name cannot be spelled in that. #68 opened a channel
that can carry one anyway, by having the bot write a directive into its status
text and the host read it every tick, and this is the second directive on it.

The argument for the whole change is one name:

    Amarr VIII (Oris) - Emperor Family Academy

`getKeyboardKeyToEnterChar` has no parenthesis at all, and `-` maps to
`vkey_SUBTRACT`, which is absent from `botlab_host.py`'s `_VK_TO_CGKEYCODE` and
so presses nothing. The search bar therefore types a *substring* and matches the
full name against the rows that come back -- a workaround that failed live in
run 17, 192 times. ESI takes the whole string.

Four things have cases here.

**The two languages must agree on the token.** The host scans a free-prose field
for it, so a drift reads exactly like a bot that never asked: no route, no
error, the search bar quietly carrying on. Pinned in #30's pattern, alongside a
check that ordinary prose and a mission name cannot produce it -- and that the
two directives on this channel do not read each other's arguments.

**The host must not call ESI every tick.** The bot re-derives its decision every
reading, so the ask stands for as long as it wants the route. The host acts on a
*change* of destination, and forgets when the ask goes away, which is #68's
lease shape rather than a high-water mark that would suppress the same station
asked for again later.

**The search bar has to remain.** It needs no credentials, works from a cold
start, and #67 is fixing a real bug in it. So the choice is read out of the
source: which mechanism is preferred, what turns the preference off, and what
happens when the ask is not answered.

**Nothing token-shaped may travel this way.** The directive goes through the
status text, which `log_decision` prints on every reading. A station name is
fine there; a refresh token or an OAuth error body is not. #23 pinned that for
the volatile-process request, and this path runs the same code, so the sentinel
cases below pin it for the directive too.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
HOST_PY = os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py")

sys.path.insert(0, MACOS_HOST_DIR)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
import esi_waypoint  # noqa: E402
import botlab_host  # noqa: E402

# The whole argument for this change, in one string: a parenthesis has no key at
# all and `-` maps to a virtual key the host cannot press.
UNTYPABLE_STATION = "Amarr VIII (Oris) - Emperor Family Academy"

# What a leak would look like. Same sentinel as test_esi_destination.py.
SENTINEL = "REFRESH-TOKEN-THAT-MUST-NOT-BE-LOGGED"


def bot_source():
    with open(BOT_ELM, encoding="utf-8") as source:
        return source.read()


def host_source():
    with open(HOST_PY, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Source text with every run of whitespace reduced to one space.

    Every assertion that reads source goes through this, and the expected
    strings are written the same way. PR #58 is why: an `elm-format` pass moved
    where lines happened to break and broke three tests that had asserted on the
    old layout. What these mean is the structure, not its typography.
    """
    return " ".join(text.split())


def elm_string_constant(source, name):
    match = re.search(r'^%s =\n\s*"([^"]*)"' % re.escape(name), source, re.M)
    assert match, "could not find %s in Bot.elm" % name
    return match.group(1)


def elm_int_constant(source, name):
    match = re.search(r"^%s =\n\s*(-?\d+)" % re.escape(name), source, re.M)
    assert match, "could not find %s in Bot.elm" % name
    return int(match.group(1))


def elm_function_body(source, name):
    """One top-level definition's body, from its `name x =` to the next blank
    pair of lines, whitespace-collapsed."""
    match = re.search(r"^%s [^\n]*=\n(.*?)(?=\n\n\n)" % re.escape(name),
                      source, re.M | re.S)
    assert match, "could not find %s in Bot.elm" % name
    return collapsed(match.group(1))


@contextlib.contextmanager
def patched(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


class TheTwoLanguagesAgreeOnTheDirective(unittest.TestCase):
    """A drift here is silent in the worst direction: the bot asks, the host
    does not hear, and the log of both sides looks like a bot that never
    asked."""

    def setUp(self):
        self.source = bot_source()

    def test_the_host_pattern_starts_with_the_prefix_the_bot_writes(self):
        prefix = elm_string_constant(self.source, "hostDirectivePrefix")
        pattern = botlab_host.BOT_DIRECTIVE_SET_DESTINATION.pattern
        self.assertTrue(
            pattern.startswith(re.escape(prefix).replace("\\ ", " ")),
            "host pattern %r does not start with the bot's prefix %r"
            % (pattern, prefix))

    def test_both_directives_share_one_prefix(self):
        """Two conventions on one channel would drift; #68 chose this token."""
        self.assertTrue(
            botlab_host.BOT_DIRECTIVE_EXTEND_SESSION.pattern.startswith("@host "))
        self.assertTrue(
            botlab_host.BOT_DIRECTIVE_SET_DESTINATION.pattern.startswith("@host "))

    def test_the_verb_the_bot_writes_is_the_verb_the_host_matches(self):
        built = elm_function_body(self.source, "hostDirectiveSetDestination")
        self.assertIn('hostDirectivePrefix ++ "set-destination " ++ stationName',
                      built)
        self.assertIn("set-destination ",
                      botlab_host.BOT_DIRECTIVE_SET_DESTINATION.pattern)

    def test_the_untypable_name_survives_the_round_trip(self):
        """The name is the argument for the feature, and it is also the one
        most likely to break a regex: two parentheses and a hyphen."""
        directive = "@host set-destination " + UNTYPABLE_STATION
        self.assertEqual(UNTYPABLE_STATION,
                         botlab_host.bot_requested_destination(directive))

    def test_a_real_status_text_parses(self):
        """Built the way a reading's really is: the status lines from
        `statusTextFromState`, then the decision path, which is where the
        directive lives -- see `BotFrameworkSeparatingMemory`, which joins the
        two."""
        status = "\n".join([
            "Mission: Technological Secrets (3 of 3) -- no instruction",
            "ship ok | Home station: drone bay last seen empty.",
            "+ Wind down: head for the home station.",
            "++ Ask the host to set the route to '%s' through ESI, which can "
            "name a station this bot cannot type." % UNTYPABLE_STATION,
            "+++ @host set-destination " + UNTYPABLE_STATION,
            "++++ Wait for progress in game.",
        ])
        self.assertEqual(UNTYPABLE_STATION,
                         botlab_host.bot_requested_destination(status))

    def test_the_two_directives_do_not_read_each_others_arguments(self):
        status = "\n".join([
            "+++ @host set-destination " + UNTYPABLE_STATION,
            "@host extend-session 480",
        ])
        self.assertEqual(UNTYPABLE_STATION,
                         botlab_host.bot_requested_destination(status))
        self.assertEqual(480.0, botlab_host.bot_requested_overrun_seconds(status))

    def test_the_token_cannot_be_produced_by_ordinary_prose(self):
        for innocent in [
            "Mission: The Score -- no instruction (next step: Dock)",
            "Home station: '%s'." % UNTYPABLE_STATION,
            "Set destination to '%s'." % UNTYPABLE_STATION,
            "set destination " + UNTYPABLE_STATION,
            "@host",
            "@host extend-session 480",
            "the agent said host set-destination somewhere",
        ]:
            with self.subTest(innocent=innocent):
                self.assertIsNone(botlab_host.bot_requested_destination(innocent))

    def test_nothing_asked_is_nothing_to_do(self):
        self.assertIsNone(botlab_host.bot_requested_destination(""))
        self.assertIsNone(botlab_host.bot_requested_destination(None))

    def test_an_empty_argument_is_not_a_destination(self):
        """`@host set-destination ` with nothing after it must not resolve to
        the empty string, which `set_destination` would carry to ESI."""
        self.assertIsNone(botlab_host.bot_requested_destination(
            "@host set-destination    "))


class TheHostActsOnAChangeNotOnEveryTick(unittest.TestCase):
    """Read out of the loop, because these properties are about where the call
    sits rather than what the parser returns. The bot re-derives its decision
    every reading, so the ask stands on every reading it wants the route."""

    def setUp(self):
        self.source = collapsed(host_source())

    def test_the_ask_is_read_from_this_tick_not_remembered(self):
        self.assertIn(
            'requested_destination = bot_requested_destination(cont.get("statusText"))',
            self.source)

    def test_only_a_change_of_destination_is_acted_on(self):
        self.assertIn(
            "if requested_destination != last_requested_destination: "
            "last_requested_destination = requested_destination "
            "if requested_destination is not None:",
            self.source)

    def test_an_ask_that_goes_away_is_forgotten(self):
        """So the same station asked for again later is acted on again. The
        assignment above is unconditional, which is what does it -- a
        high-water mark would suppress the second trip home of a session."""
        self.assertNotIn(
            "if requested_destination is not None and "
            "requested_destination != last_requested_destination:",
            self.source)
        self.assertIn("last_requested_destination = None", self.source)

    def test_the_grant_is_announced(self):
        self.assertIn("the bot asked for the route to", self.source)

    def test_it_reuses_the_request_handler_rather_than_a_second_path(self):
        """One code path for both ways in, so a failure cannot be reported two
        different ways -- #23's `Completed`/`Failed` shapes and its token
        discipline come along unchanged."""
        self.assertIn("dispatcher.volatile._set_autopilot_destination(", self.source)
        self.assertIn('{"name": requested_destination}', self.source)

    def test_it_sits_between_ticks_beside_the_deadline_check(self):
        """The ESI call blocks this loop, so the bot's next reading is taken
        after it finished -- which is what makes the route panel a confirmation
        one reading later. Mid-tick it would cut a dispatched input sequence in
        half."""
        deadline = self.source.index("granted_seconds = bot_requested_overrun_seconds")
        route = self.source.index("requested_destination = bot_requested_destination")
        notify = self.source.index('notify = cont.get("notifyWhenArrivedAtTime")')
        self.assertLess(deadline, route)
        self.assertLess(route, notify)


class TheSearchBarRemains(unittest.TestCase):
    """#67 is fixing a real bug in the search-bar sequence, and that sequence is
    the only one that works with no ESI credentials and from a cold start. ESI
    is preferred; it does not replace it."""

    def setUp(self):
        self.source = bot_source()
        self.collapsed = collapsed(self.source)

    def test_the_search_bar_is_what_the_preference_falls_through_to(self):
        body = elm_function_body(self.source, "routeToStation context stationName")
        self.assertIn("if esiRouteIsPreferred context stationName then", body)
        self.assertIn("else routeToStationByName context stationName", body)

    def test_the_search_bar_sequence_is_still_the_one_this_bot_had(self):
        """Its steps are what #67 is working on, so this change must not have
        rewritten any of them."""
        body = elm_function_body(self.source, "routeToStationByName context stationName")
        for step in [
            'withinWindow window "Set Destination"',
            'withinWindow resultsWindow "Stations ("',
            "searchInputField context",
            "typeTextEffects query",
        ]:
            with self.subTest(step=step):
                self.assertIn(step, body)

    def test_a_setting_turns_the_ask_off_outright(self):
        self.assertIn('( "route-by-esi" , AppSettings.valueTypeYesOrNo', self.collapsed)
        self.assertIn("routeByEsi : AppSettings.YesOrNo", self.collapsed)

    def test_the_ask_is_the_default(self):
        self.assertIn("routeByEsi = AppSettings.Yes", self.collapsed)

    def test_the_preference_is_gated_on_that_setting(self):
        body = elm_function_body(self.source, "esiRouteIsPreferred context stationName")
        self.assertIn(
            "(context.eventContext.botSettings.routeByEsi == AppSettings.Yes)", body)

    def test_the_ask_does_not_preempt_a_search_already_under_way(self):
        """Otherwise the two mechanisms take turns and neither finishes: the
        ask waits, the search bar's window sits open, and the sequence never
        gets its next click."""
        body = elm_function_body(self.source, "esiRouteIsPreferred context stationName")
        self.assertIn("(searchResultsWindow context == Nothing)", body)
        self.assertIn(
            "(stationInfoWindowForStation context stationName == Nothing)", body)

    def test_an_unanswered_ask_falls_back_rather_than_waiting_forever(self):
        body = elm_function_body(self.source, "esiRouteIsPreferred context stationName")
        self.assertIn(
            "not (esiRouteAskHasGoneUnanswered context.previousStepsEffects)", body)

    def test_the_fallback_window_is_short_and_bounded(self):
        """Long enough for the client's route panel to catch up, short enough
        that a host which cannot set a route costs a few readings rather than a
        trip. The host acts between ticks and blocks, so one reading would
        nearly do."""
        readings = elm_int_constant(self.source, "esiRouteReadingsBeforeSearchBar")
        self.assertGreaterEqual(readings, 1)
        self.assertLessEqual(readings, 10)

    def test_every_route_setting_call_site_goes_through_the_choice(self):
        """A caller left on `routeToStationByName` would silently never use ESI
        -- and would look exactly like one that had."""
        callers = re.findall(
            r"^\s*\(?routeToStationByName context stationName(?! =)",
            self.source, re.M)
        self.assertEqual(
            1, len(callers),
            "routeToStationByName should be reached only from routeToStation")


class TheRouteIsOnlyBelievedToBeOurs(unittest.TestCase):
    """The route panel says a destination exists, never which one. Following a
    leftover mission route home is not a visible failure: the ship travels,
    docks, and every log line reads like success."""

    def setUp(self):
        self.source = bot_source()

    def test_either_mechanism_can_supply_the_evidence(self):
        body = elm_function_body(self.source, "homeStationRouteIsSet context stationName")
        self.assertIn("routeIsSet context", body)
        self.assertIn("context.memory.routeAppearedWithoutInput", body)
        self.assertIn("stationInfoWindowForStation context stationName /= Nothing",
                      body)

    def test_the_esi_evidence_is_that_no_input_was_dispatched(self):
        """Setting a destination in the client takes a click. The ask takes
        none, so a route appearing across a silent step was set from outside."""
        body = elm_function_body(
            self.source, "previousStepsEffectsDispatchedNothing previousStepsEffects")
        self.assertIn("List.head", body)
        self.assertIn("Maybe.map List.isEmpty", body)
        self.assertIn("Maybe.withDefault False", body)

    def test_the_latch_has_only_the_four_branches_it_should(self):
        """Written out rather than described, so pinning it at `True` -- which
        would have the bot follow any route it found -- fails here."""
        latch = re.search(
            r"routeAppearedWithoutInput =\n(.*?)(?=\n    , lootedWreckIds)",
            self.source, re.S)
        self.assertIsNotNone(latch)
        body = collapsed(re.sub(r"--[^\n]*", "", latch.group(1)))
        self.assertIn("if not routeIsSetNow then False", body)
        self.assertIn("else if botMemoryBefore.routeAppearedWithoutInput then True",
                      body)
        self.assertIn(
            "else not botMemoryBefore.routeWasSetInLastReading "
            "&& previousStepDispatchedNoInput",
            body)

    def test_the_latch_is_cleared_when_the_route_is(self):
        """It can never outlive the route it describes."""
        latch = re.search(
            r"routeAppearedWithoutInput =\n(.*?)(?=\n    , lootedWreckIds)",
            self.source, re.S)
        self.assertIn("if not routeIsSetNow then False",
                      collapsed(re.sub(r"--[^\n]*", "", latch.group(1))))

    def test_the_standing_ask_names_the_station_being_flown_to(self):
        """The latch records that *a* route came from the host, not which one --
        a reading cannot name a destination. Re-asserting it every travelling
        reading is what stops a bot that changed its mind reading a standing
        route as the route to somewhere else."""
        body = elm_function_body(
            self.source,
            "keepAskingTheHostForThisRoute context stationName continueWith")
        self.assertIn("context.memory.routeAppearedWithoutInput", body)
        self.assertIn("describeBranch (hostDirectiveSetDestination stationName) "
                      "continueWith", body)
        self.assertIn("else continueWith", body)

    def test_a_route_the_search_bar_set_is_not_reasserted(self):
        body = elm_function_body(
            self.source,
            "keepAskingTheHostForThisRoute context stationName continueWith")
        self.assertIn(
            "(context.eventContext.botSettings.routeByEsi == AppSettings.Yes) "
            "&& context.memory.routeAppearedWithoutInput",
            body)


class NothingTokenShapedTravelsThisWay(unittest.TestCase):
    """The directive rides the status text, which `log_decision` prints on every
    reading. A station name is fine there. #23 pinned the request path; this
    pins the directive path, which runs the same code."""

    def quoting_urlopen(self, request, timeout=None):
        body = json.dumps({"error": "invalid_grant",
                           "error_description": f"bad token {SENTINEL}"}).encode()
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    def act_on(self, status_text):
        """What `run_bot` does with a tick's status text, minus the loop."""
        name = botlab_host.bot_requested_destination(status_text)
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            print(f"# the bot asked for the route to {name!r} "
                  f"-- setting it through ESI", file=sys.stderr)
            result = botlab_host.VolatileHost()._set_autopilot_destination(
                {"name": name})
        return result, captured.getvalue()

    def test_a_failing_ask_leaks_the_token_into_neither_result_nor_log(self):
        directive = "@host set-destination " + UNTYPABLE_STATION
        with patched(esi_waypoint, "_ID_BY_NAME", {UNTYPABLE_STATION.lower(): 60008950}), \
                patched(esi_waypoint, "keychain_load", lambda: SENTINEL), \
                patched(esi_waypoint, "client_id", lambda: "client"), \
                patched(esi_waypoint.urllib.request, "urlopen", self.quoting_urlopen):
            result, log = self.act_on(directive)
        self.assertNotIn("Completed", result)
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn(SENTINEL, log)
        self.assertIn(UNTYPABLE_STATION, log)

    def test_the_failure_reaches_the_log_as_itself(self):
        """A destination that silently was not set, followed by travel logic
        finding no route, is this repo's signature failure."""
        def refuse(**kwargs):
            raise esi_waypoint.EsiError("refused (403): the token needs "
                                        "esi-ui.write_waypoint.v1")

        with patched(esi_waypoint, "set_destination", refuse):
            result, log = self.act_on("@host set-destination " + UNTYPABLE_STATION)
        self.assertIn("Failed", result)
        self.assertIn("esi-ui.write_waypoint.v1", log)

    def test_the_status_text_is_never_treated_as_a_credential(self):
        """Everything the parser hands on is a name. Read out of the source so
        that a future argument cannot quietly become something else."""
        body = collapsed(re.search(
            r"def bot_requested_destination\(status_text\):(.*?)\n\n\n",
            host_source(), re.S).group(1))
        self.assertIn("name = match.group(1).strip()", body)
        self.assertIn("return name or None", body)


def elm_is_available():
    return shutil.which("elm") is not None


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version`,
    build there, never in the checked-in source, and open the module's exports
    so the repl can reach more than `botMain`.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-set-destination-")
        self.app = os.path.join(self.scratch, "app")
        shutil.copytree(MISSION_RUNNER_DIR, self.app)

        version = subprocess.run(
            ["elm", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
        elm_json = os.path.join(self.app, "elm.json")
        with open(elm_json, encoding="utf-8") as source:
            patched_json = source.read().replace(
                '"elm-version": "0.19.1"', '"elm-version": "%s"' % version)
        with open(elm_json, "w", encoding="utf-8") as target:
            target.write(patched_json)

        bot = os.path.join(self.app, "Bot.elm")
        with open(bot, encoding="utf-8") as handle:
            source = handle.read()
        opened = re.sub(r"module Bot exposing\s*\([^)]*\)",
                        "module Bot exposing (..)", source, count=1)
        assert opened != source, "could not open Bot.elm's exports"
        with open(bot, "w", encoding="utf-8") as handle:
            handle.write(opened)

    def ask(self, expressions):
        script = ("import Bot exposing (..)\n"
                  "import Common.EffectOnWindow as EffectOnWindow\n"
                  + "".join(expression + "\n" for expression in expressions))
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        return plain, result.stderr

    def booleans(self, expressions):
        plain, stderr = self.ask(expressions)
        answers = [answer == "True"
                   for answer in re.findall(r"(True|False) : Bool", plain)]
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def strings(self, expressions):
        plain, stderr = self.ask(expressions)
        # A long answer is wrapped onto its own line before the ` : String`,
        # so the type annotation is matched across whatever whitespace the repl
        # chose rather than only at the end of the same line.
        answers = re.findall(r'"((?:[^"\\]|\\.)*)"\s*: String', plain)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return [answer.replace('\\"', '"').replace("\\\\", "\\")
                for answer in answers]

    def works(self):
        """A probe on something this change does not touch, so a mutation to
        what is under test fails a case rather than skipping the whole class."""
        plain, stderr = self.ask(['missionNameForDeclining "x"'])
        return '"x" : String' in plain, plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheRulesAreExecutedRatherThanMirrored(unittest.TestCase):
    """The suite is Python and reads `Bot.elm` as text, which is fine for
    structure and a trap for behaviour. These three run for real."""

    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        usable, output = cls.repl.works()
        if not usable:
            cls.repl.close()
            raise unittest.SkipTest(
                "elm repl cannot evaluate here, so these rules are unchecked "
                "by execution in this environment:\n" + output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_directive_the_bot_builds_is_the_one_the_host_parses(self):
        """The cross-language coupling, end to end: Elm builds the line and the
        host's own regex reads the name back out of it."""
        built = self.repl.strings([
            "hostDirectiveSetDestination " + json.dumps(UNTYPABLE_STATION),
            'hostDirectiveSetDestination "Jita IV - Moon 4 - Caldari Navy Assembly Plant"',
        ])
        self.assertEqual(
            "@host set-destination " + UNTYPABLE_STATION, built[0])
        for line, expected in zip(built, [
                UNTYPABLE_STATION,
                "Jita IV - Moon 4 - Caldari Navy Assembly Plant"]):
            with self.subTest(line=line):
                self.assertEqual(
                    expected, botlab_host.bot_requested_destination(line))

    def test_the_unanswered_rule_needs_a_full_window_of_silence(self):
        readings = elm_int_constant(bot_source(), "esiRouteReadingsBeforeSearchBar")
        silent = "[" + ",".join(["[]"] * readings) + "]"
        one_short = "[" + ",".join(["[]"] * (readings - 1)) + "]"
        interrupted = ("[[],[EffectOnWindow.KeyDown EffectOnWindow.vkey_RETURN]"
                       + ",[]" * (readings - 2) + "]")
        answers = self.repl.booleans([
            "esiRouteAskHasGoneUnanswered " + silent,
            "esiRouteAskHasGoneUnanswered " + one_short,
            "esiRouteAskHasGoneUnanswered []",
            "esiRouteAskHasGoneUnanswered " + interrupted,
        ])
        self.assertEqual([True, False, False, False], answers)

    def test_a_fresh_session_still_gets_to_ask(self):
        """An empty history is not a run of silence -- reading it as one would
        send the very first route straight to the search bar."""
        self.assertEqual([False], self.repl.booleans([
            "esiRouteAskHasGoneUnanswered []"]))

    def test_a_step_that_dispatched_input_is_not_silent(self):
        answers = self.repl.booleans([
            "previousStepsEffectsDispatchedNothing [[]]",
            "previousStepsEffectsDispatchedNothing "
            "[[EffectOnWindow.KeyDown EffectOnWindow.vkey_RETURN],[]]",
            "previousStepsEffectsDispatchedNothing []",
        ])
        self.assertEqual([True, False, False], answers)


if __name__ == "__main__":
    unittest.main()
