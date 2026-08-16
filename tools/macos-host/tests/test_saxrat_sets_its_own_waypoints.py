"""saxrat originating its own route, rather than waiting for a human to set one.

`eve-online-saxrat` could always *follow* a route -- `jumpToNextSystem` right
clicks the route panel's first marker and takes the jump entry -- but it could
never create one. With the anomalies in a system exhausted and no route set, it
fell through to `tetherAtStructure` and parked, and `noProbeScanResultsAndNo
RouteLastTimeInSpace` exists precisely because it would otherwise undock
straight back into the same dead end. Moving to the next system was a human's
job.

The gap was never the travelling. It was that a solar system name cannot be
spelled in the vocabulary a decision has: `OperateBotConfiguration` gives a
running bot `buildTaskFromEffectSequence`, whose alphabet is mouse moves,
buttons, keys and scroll, and every `RequestToVolatileProcess` is issued by
`getNextSetupTask`'s closed setup state machine that a decision cannot reach.
So the ask rides `ContinueSession.statusText`, which the host already reads
every tick, behind a token ordinary prose cannot produce.

**The cross-language pin is the case that matters most here.** The bot writes
the directive and `botlab_host.py` matches it with a regex, in two languages
that no compiler checks against each other. A drift is silent in the worst
direction: the bot reports asking, the host never sees it, and the symptom is a
bot that parks -- which is exactly what it did before the feature existed.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import REPO_DIR, open_repl
from test_saxrat_ported_guards import SaxratRepl as PortedGuardsRepl
from test_saxrat_route_to_the_system_we_are_in import location_panel, pick

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")
BOTLAB_HOST_PY = os.path.join(
    REPO_DIR, "tools", "macos-host", "botlab_host", "botlab_host.py")

# The parser imports come with the readings: since #262 the picker takes the
# reading the ship's own location panel is in, so these cases hand it one the
# real `EveOnline.ParseUserInterface` produced rather than a record built here.
PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# Real solar system names from this repo's own recorded runs and CLAUDE.md.
# `Amarr VIII (Oris) - Emperor Family Academy` is the station that motivated
# ESI in the first place; the *system* names below are the easy case, which is
# the point -- `/universe/ids/` indexes them directly where it does not index
# every NPC station.
SYSTEMS = ["Irnin", "Amarr", "Sizamod"]


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def body_of(source, name):
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


# Somewhere the circuit does not name. `nextHuntingGroundFrom` skips a hunting
# ground the ship is standing in (#262), so the rotation these cases are about
# is only visible from a reading taken somewhere else -- which is where the
# circuit spends nearly all of its readings anyway.
ELSEWHERE = "Jita IV"


class SaxratRepl(PortedGuardsRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-waypoint-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    @staticmethod
    def settings(hunt=(), home=None):
        """A `BotSettings` with only the two fields these cases care about."""
        return "{ defaultBotSettings | huntSystemNames = [ %s ], homeSystemName = %s }" % (
            ", ".join('"%s"' % name for name in hunt),
            'Just "%s"' % home if home else "Nothing")

    def elsewhere(self):
        """A real parsed reading naming a system that is not on the circuit."""
        return [self.reading_binding("elsewhere", [location_panel(ELSEWHERE)])]


class TheDirectiveTheHostActuallyMatches(unittest.TestCase):
    """One token, two languages, and nothing that checks them against each other.

    So it is checked here, in both directions: what the bot writes is fed to the
    host's own compiled regex, and the host's pattern is read back out of
    `botlab_host.py` rather than restated.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def host_pattern(self):
        source = source_of(BOTLAB_HOST_PY)
        match = re.search(
            r"BOT_DIRECTIVE_SET_DESTINATION = re\.compile\(r\"([^\"]+)\"\)",
            source)
        self.assertIsNotNone(
            match,
            "botlab_host.py no longer defines BOT_DIRECTIVE_SET_DESTINATION, "
            "so the bot is writing a directive into the void")
        return re.compile(match.group(1))

    def test_what_the_bot_writes_is_what_the_host_matches(self):
        written = self.repl.strings(
            ['hostDirectiveSetDestination "%s"' % name for name in SYSTEMS])
        pattern = self.host_pattern()
        for name, line in zip(SYSTEMS, written):
            found = pattern.search(line)
            self.assertIsNotNone(
                found,
                "the host's own regex does not match what the bot writes for "
                "%r: %r" % (name, line))
            self.assertEqual(
                name, found.group(1),
                "the host would set the destination to something other than "
                "the system the bot named")

    def test_the_directive_survives_being_embedded_in_prose(self):
        """The bot does not write the token alone -- it is the tail of a whole
        decision sentence, because that sentence is what an operator reads."""
        [sentence] = self.repl.strings(
            ['hostDirectivePrefix ++ "set-destination " ++ "Irnin"'])
        self.assertIsNotNone(
            self.host_pattern().search(
                "Nothing left to hunt here. " + sentence + "\\nnext line"))

    def test_ordinary_prose_cannot_produce_the_token(self):
        """The whole point of a prefix: a status line that merely *talks* about
        a destination must not set one."""
        pattern = self.host_pattern()
        for innocent in ["set-destination Irnin",
                         "the host set-destination for Irnin",
                         "Asking about a destination: Irnin"]:
            self.assertIsNone(
                pattern.search(innocent),
                "prose without the prefix was read as a directive: %r"
                % innocent)


class TheCircuitRotates(unittest.TestCase):
    """The rotation, executed rather than described.

    A "first name that is not the system we are in" rule ping-pongs between the
    first two entries and never reaches the third, which is why an index exists
    at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_walks_the_list_in_order_and_wraps(self):
        settings = self.repl.settings(hunt=SYSTEMS)
        answers = self.repl.strings(
            ["%s |> Maybe.withDefault \"nowhere\""
             % pick(settings, index, "elsewhere")
             for index in range(len(SYSTEMS))],
            self.repl.elsewhere())
        self.assertEqual(
            answers, SYSTEMS,
            "the circuit does not visit its systems in the order they were "
            "configured")

    def test_a_completed_lap_falls_back_to_the_home_system(self):
        with_home = self.repl.settings(hunt=SYSTEMS, home="Jita")
        without = self.repl.settings(hunt=SYSTEMS)
        answers = self.repl.strings(
            ["%s |> Maybe.withDefault \"nowhere\""
             % pick(with_home, 3, "elsewhere"),
             "%s |> Maybe.withDefault \"nowhere\""
             % pick(with_home, 5, "elsewhere"),
             # With no home system the circuit simply keeps going round, which
             # is the right answer for a ratting bot: anomalies respawn.
             "%s |> Maybe.withDefault \"nowhere\""
             % pick(without, 3, "elsewhere")],
            self.repl.elsewhere())
        self.assertEqual(
            answers, ["Jita", "Jita", SYSTEMS[0]],
            "a completed lap does not reach the staging system, or an absent "
            "staging system stops the circuit instead of wrapping it")

    def test_no_circuit_configured_names_nowhere(self):
        answers = self.repl.evaluate(
            ["%s == Nothing" % pick(self.repl.settings(), 0, "elsewhere"),
             # A staging system alone is not a circuit: with nothing to
             # exhaust, there is no lap to complete.
             "%s == Nothing"
             % pick(self.repl.settings(home="Jita"), 0, "elsewhere"),
             "huntSystemAtIndex %s 7 == Nothing" % self.repl.settings()],
            self.repl.elsewhere())
        self.assertEqual(
            answers, [True] * 3,
            "a bot with no 'hunt-system' must name nowhere, so it parks "
            "exactly as it did before this feature existed")

    def test_the_index_is_taken_modulo_rather_than_running_off_the_end(self):
        settings = self.repl.settings(hunt=SYSTEMS)
        answers = self.repl.strings(
            ["huntSystemAtIndex %s %d |> Maybe.withDefault \"nowhere\""
             % (settings, index) for index in [0, 3, 4, 100]])
        self.assertEqual(answers, ["Irnin", "Irnin", "Amarr", "Amarr"])


class TheAskIsBoundedAndCountsTheRightThing(unittest.TestCase):
    """The bound, and the counter behind it.

    The channel is one-way and unacknowledged, so there is no reply to wait on
    and the bot repeats the ask until the client's own route panel answers. That
    is only safe if it stops.
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
        counter = update[update.index("destinationAskReadings ="):]
        return counter[:counter.index("routeSettingGivenUp =")]

    def test_the_counter_only_advances_in_the_state_the_branch_asks_from(self):
        """Issue #11's mistake is the one to avoid here: a counter that
        measures something other than the thing it bounds.

        #273 is that mistake, found in this counter and in the direction the
        case as first written could not see. It asserted the counter was keyed
        on `standingInADeadEnd`, which was true and was the defect: that
        predicate demanded an empty probe scanner while the branch asks on the
        wider "no anomaly matching the settings", so the counter reset on every
        ordinary reading and the bound was unreachable. It is keyed on
        `destinationAskedForNow` now -- `Just` exactly when the branch would
        ask, and for the system it would ask for -- which is what this case was
        named for. The states that must *not* count are executed in
        `test_saxrat_route_ask_bound`, over really-parsed readings, rather than
        being asserted here as a shape.
        """
        counter = self.counter_source()
        self.assertIn("if destinationAskedForNow == Nothing then", counter)
        self.assertIn("botMemoryBefore.destinationAskReadings + 1", counter,
                      "the counter never advances, so its bound is "
                      "unreachable")
        self.assertIn("then 0", counter,
                      "the counter is not cleared once the ship is no longer "
                      "in a dead end")
        self.assertNotIn(
            "if standingInADeadEnd then", counter,
            "the counter is keyed on the dead end again rather than on the "
            "destination the branch would ask for, so a bot with nowhere to "
            "ask for spends a budget it never asked against -- which is what "
            "runs 12, 26 and 27 did")

    def test_the_dead_end_needs_a_ship_no_route_and_nothing_worth_hunting(self):
        """The predicate, and the four clauses it takes to match the ask.

        `scanResults >> List.isEmpty` was the fifth and is #273: the ask fires
        on "no anomaly matching the settings", so an empty scanner is a
        narrowing that the corpus says is systematically absent rather than
        merely rarer. `anomaliesWorthHunting` is the filter the decision reads
        too.
        """
        update = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "updateMemoryForNewReadingFromGame"))
        predicate = update[update.index("standingInADeadEnd ="):]
        predicate = predicate[:predicate.index("destinationAskedForNow =")]
        self.assertIn("context.readingFromGameClient.shipUI /= Nothing",
                      predicate, "a docked reading would count as a dead end")
        self.assertIn(
            "not (routePanelShowsARoute context.readingFromGameClient)",
            predicate,
            "a ship with a route to follow would count as stuck")
        self.assertIn(
            "not (shipIsWarpingOrJumping context.readingFromGameClient)",
            predicate,
            "a ship crossing a system counts as stuck, and a warp runs longer "
            "than the whole budget")
        self.assertIn("anomaliesWorthHunting", predicate)
        self.assertIn(
            "not (gridStillHasSomethingToDo incomingDamageNow "
            "context.readingFromGameClient)",
            predicate,
            "a fight the site's own signature has dropped out of counts as a "
            "dead end, which is the case the replaced comment narrowed for")
        self.assertNotIn(
            "scanResults >> List.isEmpty", predicate,
            "the counter is back on an empty probe scanner while the ask fires "
            "on a scanner with nothing worth hunting on it, which is #273")

    def test_the_give_up_latches_for_the_session(self):
        """A host with no ESI credentials will never answer, so the give-up
        must not un-latch and start the asking over."""
        update = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "updateMemoryForNewReadingFromGame"))
        latch = update[update.index("routeSettingGivenUp ="):]
        self.assertIn("botMemoryBefore.routeSettingGivenUp ||", latch,
                      "the give-up no longer latches")
        self.assertIn(
            "routeAskGiveUpReadings < botMemoryBefore.destinationAskReadings",
            latch)

    def test_the_bound_is_a_number_somebody_chose(self):
        [bounded] = self.repl.evaluate(["routeAskGiveUpReadings == 20"])
        self.assertTrue(bounded)

    def test_the_one_picker_is_shared_with_the_decision(self):
        """Two copies of "where next" would drift, and the memory would then be
        counting readings against a system the bot was not asking for."""
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn(
            "nextHuntingGround context = nextHuntingGroundFrom "
            "context.eventContext.botSettings context.memory.huntSystemIndex "
            "context.readingFromGameClient",
            source)
        self.assertIn(
            "nextHuntingGroundFrom context.botSettings "
            "botMemoryBefore.huntSystemIndex context.readingFromGameClient",
            source,
            "the memory update names the destination some other way than the "
            "decision does")


class TheBranchIsReachableAndSaysSo(unittest.TestCase):
    """Where it sits, and what it does when there is nowhere to go.

    A feature wired nowhere compiles perfectly. `jumpToNextSystem`'s no-route
    case is the one place this belongs: it is what the anomaly hunt already
    falls through to when nothing is worth shooting.
    """

    def test_it_replaces_the_park_in_the_no_route_case(self):
        jump = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "jumpToNextSystem"))
        self.assertIn("Nothing -> setRouteToNextHuntingGround context", jump,
                      "the no-route case no longer reaches the ask, so the "
                      "bot still parks and the feature is unreachable")

    def test_every_way_out_still_ends_somewhere_safe(self):
        """Given up, nothing configured, or asking: none of the three may be a
        dead stop."""
        branch = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "setRouteToNextHuntingGround"))
        self.assertEqual(
            2, branch.count("tetherAtStructure context"),
            "the give-up and the no-circuit case must both fall back to the "
            "behaviour this bot had before the feature existed")
        self.assertIn("hostDirectiveSetDestination systemName", branch,
                      "the branch no longer writes the directive")

    def test_the_operator_can_see_the_circuit_every_reading(self):
        """Three states, in whatever words #242 left them.

        A bot with no circuit will never set a route, an ask that is going
        unanswered is the host not answering, and the give-up is the end of the
        asking. Each has to be distinguishable on a reading -- what the clause
        calls them is the status line's business and changed with #242, so the
        wording asserted here is only what the shipped clause says today.
        """
        describe = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                     "describeHuntCircuit"))
        self.assertIn("no hunt circuit", describe,
                      "a bot that will never set a route does not say so")
        self.assertIn("ROUTE SETTING GIVEN UP", describe)
        self.assertIn("routeAskGiveUpReadings", describe,
                      "an ask that is going unanswered is invisible -- the "
                      "clause names neither how long it has waited nor the "
                      "bound it is waiting against")

    def test_the_status_line_actually_carries_it(self):
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn("++ describeHuntCircuit context", source,
                      "describeHuntCircuit is never called, so none of the "
                      "above reaches an operator")


class TheSettingsAreRealSettings(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_are_parsed(self):
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn('( "hunt-system"', source)
        self.assertIn('( "home-system"', source)

    def test_the_circuit_setting_accumulates_in_the_order_written(self):
        """`anomaly-name` prepends, so repeated keys come out reversed. A
        circuit is an ordered route and must not.

        Asked of the parser rather than asserted as a substring of the handler.
        It was the substring
        `settings.huntSystemNames ++ [ String.trim systemName ]` until #182 gave
        this setting `splitSettingIntoNames`, which changed the shape while
        leaving the property -- so the case went red for a change that could not
        break what it exists to protect, which is what a shape assertion buys.
        The comma form's own ordering is in
        `test_saxrat_comma_split_settings.TheSettingsAreStillRepeatableTest`.
        """
        self.assertEqual(
            self.repl.evaluate([
                '(parseBotSettings "hunt-system=A\\nhunt-system=B"'
                ' |> Result.map .huntSystemNames) == Ok ["A","B"]']),
            [True],
            "the circuit is built by prepending, so it would be walked in the "
            "reverse of the order it was configured in")

    def test_both_are_documented_where_bot_help_reads_them(self):
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn("`hunt-system`: Name of a solar system", source)
        self.assertIn("`home-system`: Name of the solar system", source)

    def test_the_defaults_leave_an_existing_settings_string_alone(self):
        defaults = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                     "defaultBotSettings"))
        self.assertIn("huntSystemNames = []", defaults)
        self.assertIn("homeSystemName = Nothing", defaults)


if __name__ == "__main__":
    unittest.main()
