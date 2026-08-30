"""Tests for reading the route panel's own jump count off its markers.

Issue #171. `dockAtDestinationStation`'s `destinationIsInThisSystem` used to be
`routeElementMarker |> List.length |> (==) 1` -- one marker meaning "the
destination is here and there is nothing further to jump to". Read live while
PR #170 was written, one jump out: the route panel's header said `Route 1
Jump`, there was **one** marker, and it carried `solarSystemID 30005001`,
`destinationID 60012607` (a station) and **`numJumps 1`** -- one jump away, not
in this system. A 2019 recording in `explore/` agrees from the other end:
`3 Jumps`, three markers. So the marker count is jumps *remaining*, not
waypoints, and the old condition was true one system early on every route that
had exactly one jump left.

`numJumps` was already on the marker in the client's own tree;
`ParseUserInterface` just never read it. `InfoPanelRouteRouteElementMarker`
now carries `numJumps : Maybe Int`, identically across every vendored copy
that carries #171 -- `TheVendoredCopiesTest` pins that -- and
`destinationIsInThisSystemFromRouteMarkers`
asks the marker's own count rather than how many icons are drawn: exactly one
marker, and that marker's `numJumps` reading `Just 0`.

**What the client writes on genuine arrival is still unread.** Every live
reading available had at least one jump remaining, so whether `numJumps` there
is `Just 0`, `Nothing`, or something else this rule has never been asked about
is not established. The rule is written to fail closed on that: an empty list,
several markers, or an unreadable/nonzero `numJumps` all answer `False` and
send `dockAtDestinationStation` to its cascade fall-back, exactly as an
unreachable marker count already did.

**#98's guard is untouched.** `stationIsTheOneJustUndockedFrom` is what kept
the old bug from costing a run anything observed, for a reason that has
nothing to do with route markers, and nothing here removes or weakens it --
`TheGuardIsStillConsultedTest` pins that the branch this rule feeds still asks
it before docking.

The parser is executed through the real `EveOnline.ParseUserInterface` --
readings are built as raw UI trees and decoded with
`decodeMemoryReadingFromString` and `parseUserInterfaceFromUITree`, the way
`test_target_hitpoints.py` and `test_quick_message_logged.py` do -- and the
rule is executed through the real `Bot.elm` in `elm repl`, both via the shared
harness in `prerequisites.py`. Nothing here reads a live game client or drives
a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import itertools
import os
import re
import unittest

from prerequisites import (ElmRepl, MISSION_RUNNER_DIR, REPO_DIR,
                            elm_json_literal, open_repl)

APP_DIRS = {
    "eve-online-warp-to-0-autopilot": os.path.join(
        REPO_DIR, "implement", "applications", "eve-online",
        "eve-online-warp-to-0-autopilot"),
    "eve-online-combat-anomaly-bot": os.path.join(
        REPO_DIR, "implement", "applications", "eve-online",
        "eve-online-combat-anomaly-bot"),
    "eve-online-saxrat": os.path.join(
        REPO_DIR, "implement", "applications", "eve-online",
        "eve-online-saxrat"),
    "eve-online-mission-runner": MISSION_RUNNER_DIR,
    "eve-online-mining-bot": os.path.join(
        REPO_DIR, "implement", "applications", "eve-online",
        "eve-online-mining-bot"),
}

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
MISSION_RUNNER_BOT_FRAMEWORK_ELM = os.path.join(
    MISSION_RUNNER_DIR, "EveOnline", "BotFramework.elm")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

_address = itertools.count(100000)


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


def marker(num_jumps=None, x=0, extra=None):
    """One `AutopilotDestinationIcon`, the way the route panel draws one.

    `num_jumps` of `None` leaves the `numJumps` key out of the node entirely,
    which is a marker this reading cannot read a jump count from -- distinct
    from a marker that carries the key with some other value.
    """
    entries = dict(extra or {})
    if num_jumps is not None:
        entries["numJumps"] = num_jumps
    return node("AutopilotDestinationIcon", entries, region=(x, 0, 8, 8))


def route_tree(markers):
    """A `UIRoot` holding exactly the route panel markers given."""
    info_panel_route = node(
        "InfoPanelRoute", {}, [marker_node for marker_node in markers],
        region=(0, 0, 200, 40))
    info_panel_container = node(
        "InfoPanelContainer", {}, [info_panel_route], region=(0, 0, 200, 200))
    return node("UIRoot", {}, [info_panel_container], region=(0, 0, 1920, 1080))


def reading_binding(name, markers):
    """A `let`-free binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what the cases assert on is what the
    bot would have been handed rather than a record written out by hand. See
    `elm_json_literal`'s own doc comment for why the literal is built there
    and not with a triple-quoted string.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, elm_json_literal(route_tree(markers)))


def route_markers_expression(reading_name):
    return ("(%s |> Maybe.andThen .infoPanelContainer"
            " |> Maybe.andThen .infoPanelRoute"
            " |> Maybe.map .routeElementMarker"
            " |> Maybe.withDefault [])" % reading_name)


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    return " ".join(text.split())


def without_comments(text):
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(name, source):
    match = re.search(r"^%s\s*:.*?(?=\n\n\n|\Z)" % re.escape(name),
                      source, re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def parser_file(app_key):
    return os.path.join(
        APP_DIRS[app_key], "EveOnline", "ParseUserInterface.elm")


def marker_type_alias_block(source):
    start = source.index("type alias InfoPanelRouteRouteElementMarker =")
    end = source.index("\n\n\n", start)
    return source[start:end]


def parse_function_block(source):
    start = source.index(
        "parseInfoPanelRouteFromInfoPanelContainer :")
    end = source.index("\n\n\n", start)
    return source[start:end]


class MissionRunnerRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "route-num-jumps-repl-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class TheParserTest(unittest.TestCase):
    """`numJumps`, decoded off a real `AutopilotDestinationIcon` node."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(MissionRunnerRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def num_jumps_list(self, markers):
        definitions = [reading_binding("reading", markers)]
        answers = self.repl.values(
            ["%s |> List.map .numJumps |> Debug.toString"
             % route_markers_expression("reading")],
            r'"(.*?)"\s*: String',
            definitions=definitions)
        return answers[0]

    def test_the_live_reading_s_marker_carries_numjumps_1(self):
        """The exact reading #171 was filed on: one marker, `numJumps 1`."""
        self.assertEqual(
            self.num_jumps_list([marker(num_jumps=1)]),
            "[Just 1]")

    def test_a_marker_with_no_numjumps_key_reads_nothing(self):
        self.assertEqual(
            self.num_jumps_list([marker(num_jumps=None)]),
            "[Nothing]")

    def test_a_marker_reading_zero_jumps_is_read_as_zero(self):
        """Unverified against the live client -- see this module's own doc
        comment -- but the decoder must not treat `0` as absent."""
        self.assertEqual(
            self.num_jumps_list([marker(num_jumps=0)]),
            "[Just 0]")

    def test_several_markers_each_keep_their_own_count(self):
        """The 2019 recording's shape: three markers, three counts."""
        self.assertEqual(
            self.num_jumps_list([
                marker(num_jumps=3, x=0),
                marker(num_jumps=2, x=10),
                marker(num_jumps=1, x=20),
            ]),
            "[Just 3,Just 2,Just 1]")

    def test_an_empty_route_panel_has_no_markers(self):
        self.assertEqual(self.num_jumps_list([]), "[]")

    def test_the_marker_still_carries_its_ui_node(self):
        """Adding the field must not have displaced the one already there."""
        definitions = [reading_binding("reading", [marker(num_jumps=1)])]
        answers = self.repl.evaluate(
            ["(%s |> List.map (.uiNode >> .uiNode >> .pythonObjectTypeName))"
             " == [ \"AutopilotDestinationIcon\" ]"
             % route_markers_expression("reading")],
            definitions=definitions)
        self.assertTrue(answers[0])


class TheRuleTest(unittest.TestCase):
    """`destinationIsInThisSystemFromRouteMarkers`, at each of its cases."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(MissionRunnerRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdict(self, markers):
        definitions = [reading_binding("reading", markers)]
        answers = self.repl.evaluate(
            ["destinationIsInThisSystemFromRouteMarkers %s"
             % route_markers_expression("reading")],
            definitions=definitions)
        return answers[0]

    def test_one_marker_one_jump_away_is_not_in_this_system(self):
        """The live reading #171 was filed on. This is the whole bug."""
        self.assertFalse(self.verdict([marker(num_jumps=1)]))

    def test_one_marker_reading_zero_jumps_is_in_this_system(self):
        self.assertTrue(self.verdict([marker(num_jumps=0)]))

    def test_one_marker_with_no_numjumps_declines(self):
        """Unreadable is not evidence either way, and the safe answer is no --
        the caller falls back to the cascade, which still travels the route."""
        self.assertFalse(self.verdict([marker(num_jumps=None)]))

    def test_no_markers_declines(self):
        self.assertFalse(self.verdict([]))

    def test_several_markers_all_reading_zero_still_decline(self):
        """The one-marker precondition is kept deliberately -- it is the only
        shape this branch has ever been observed running in, and requiring it
        alongside `numJumps` can only narrow when the branch fires."""
        self.assertFalse(self.verdict(
            [marker(num_jumps=0, x=0), marker(num_jumps=0, x=10)]))

    def test_several_markers_with_the_2019_recording_s_counts_decline(self):
        self.assertFalse(self.verdict([
            marker(num_jumps=3, x=0),
            marker(num_jumps=2, x=10),
            marker(num_jumps=1, x=20),
        ]))

    def test_the_rule_reads_nothing_but_its_own_argument(self):
        """No reading, no decision context, so a case can execute it."""
        body = collapsed(without_comments(declaration(
            "destinationIsInThisSystemFromRouteMarkers",
            source_of(MISSION_RUNNER_BOT_ELM))))
        for reached_for in ("context", "readingFromGameClient", "memory",
                             "infoPanelContainer"):
            self.assertNotIn(reached_for, body)


class TheWiringTest(unittest.TestCase):
    """What `dockAtDestinationStation` hands the rule, read out of the source."""

    def setUp(self):
        self.source = source_of(MISSION_RUNNER_BOT_ELM)

    def test_destinationIsInThisSystem_calls_the_rule_rather_than_counting(self):
        body = collapsed(without_comments(
            declaration("dockAtDestinationStation", self.source)))
        self.assertIn("destinationIsInThisSystemFromRouteMarkers", body)
        self.assertNotIn("List.length", body)

    def test_the_guard_is_still_consulted(self):
        """Issue #171 does not touch #98's guard.

        `dockAtDestinationStation` still asks `stationIsTheOneJustUndockedFrom`
        before docking, on every reading `destinationIsInThisSystem` answers
        `True` for -- a case a mutation removing that call fails.
        """
        body = collapsed(without_comments(
            declaration("dockAtDestinationStation", self.source)))
        self.assertIn(
            "if stationIsTheOneJustUndockedFrom context station then", body)

    def test_the_guard_s_own_rule_is_unedited(self):
        """`stationNameIsTheOneUndockedFrom` -- the comparison #98's guard
        rests on -- is untouched by this change: same two clauses, same
        fail-open default."""
        body = collapsed(without_comments(
            declaration("stationNameIsTheOneUndockedFrom", self.source)))
        self.assertIn("normalise rowName == normalise undockedName", body)
        self.assertIn(
            "stringContainsIgnoringCase (String.trim rowName) undockedName",
            body)
        self.assertIn("_ ->", body)
        self.assertIn("False", body)


class TheOtherConsumersAreUnaffectedTest(unittest.TestCase):
    """Whether any other reader of `routeElementMarker` depends on the count
    meaning waypoints.

    Issue #171 names two by name and asks that this be checked rather than
    assumed: `routeMarkerCascade`, which takes the first marker and right-
    clicks it, and #170's `jumpToNextSystem` / `routeStargateJump`, which reads
    the `NextWaypointPanel` label instead. Both are read out of the source
    rather than executed, because what is being checked is what a declaration
    does *not* reach for.
    """

    def setUp(self):
        self.source = source_of(MISSION_RUNNER_BOT_ELM)
        self.framework_source = source_of(MISSION_RUNNER_BOT_FRAMEWORK_ELM)

    def test_route_marker_cascade_only_reads_the_ui_node(self):
        body = collapsed(without_comments(
            declaration("routeMarkerCascade", self.source)))
        self.assertIn("infoPanelRouteFirstMarker.uiNode", body)
        self.assertNotIn("numJumps", body)
        self.assertNotIn("List.length", body)

    def test_the_first_marker_lookup_does_not_count_or_read_numjumps(self):
        body = collapsed(without_comments(declaration(
            "infoPanelRouteFirstMarkerFromReadingFromGameClient",
            self.framework_source)))
        self.assertNotIn("numJumps", body)
        self.assertNotIn("List.length", body)

    def test_the_panel_jump_path_does_not_read_the_marker_list_at_all(self):
        """#170's `routeStargateJump` identifies the gate from the route
        panel's `Next System in Route` label and the overview, never from
        `routeElementMarker`."""
        for name in ("routeStargateJump", "jumpThroughRouteStargate"):
            body = collapsed(without_comments(
                declaration(name, self.source)))
            self.assertNotIn("routeElementMarker", body)
            self.assertNotIn("numJumps", body)


#: `eve-online-mining-bot`'s tree was replaced with Viir's current upstream
#: (see CLAUDE.md), which predates #171 entirely: its
#: `InfoPanelRouteRouteElementMarker` carries only `uiNode` and its
#: `parseInfoPanelRouteFromInfoPanelContainer` reads no `numJumps` at all, so
#: it cannot be compared byte for byte against the copies that do carry
#: this field. It is excluded from `TheVendoredCopiesTest` rather than assigned a
#: shape; porting #171 into the newer base is tracked as follow-up work, not
#: done here.
WITHOUT_NUM_JUMPS = {"eve-online-mining-bot"}

APP_DIRS_WITH_NUM_JUMPS = {
    app: path for app, path in APP_DIRS.items() if app not in WITHOUT_NUM_JUMPS
}


class TheVendoredCopiesTest(unittest.TestCase):
    """The parser policy: vendored identically across the apps that carry it.

    `InfoPanelRouteRouteElementMarker` and the parse function that builds it
    are compared byte for byte across every copy that carries #171 (see
    `WITHOUT_NUM_JUMPS` for the one that does not), the way
    `test_game_log_channel.py` compares its own vendored block.

    Named for the property rather than for a count: the population lost
    `eve-online-wingus` when the 2023 host interface was retired (see
    `notes/retire-wingus.md`), and a class called `TheSixCopiesTest` would have
    gone on asserting the right thing under a name that had stopped being true.
    """

    def test_the_type_alias_is_identical_across_every_copy(self):
        blocks = {app: marker_type_alias_block(source_of(parser_file(app)))
                  for app in APP_DIRS_WITH_NUM_JUMPS}
        first_app, first_block = next(iter(blocks.items()))
        for app, block in blocks.items():
            self.assertEqual(
                block, first_block,
                "%s's InfoPanelRouteRouteElementMarker differs from %s's"
                % (app, first_app))
        self.assertIn("numJumps : Maybe Int", first_block)

    def test_the_parse_function_is_identical_across_every_copy(self):
        blocks = {app: parse_function_block(source_of(parser_file(app)))
                  for app in APP_DIRS_WITH_NUM_JUMPS}
        first_app, first_block = next(iter(blocks.items()))
        for app, block in blocks.items():
            self.assertEqual(
                block, first_block,
                "%s's parseInfoPanelRouteFromInfoPanelContainer differs "
                "from %s's" % (app, first_app))
        self.assertIn('getIntPropertyFromDictEntries "numJumps"', first_block)

    def test_every_copy_already_has_the_int_helper_it_needs(self):
        """`getIntPropertyFromDictEntries` predates this change in all five --
        confirmed rather than assumed, since a copy missing it would fail to
        compile instead of failing a case."""
        for app in APP_DIRS_WITH_NUM_JUMPS:
            source = source_of(parser_file(app))
            self.assertIn(
                "getIntPropertyFromDictEntries : String -> "
                "EveOnline.MemoryReading.UITreeNode -> Maybe Int",
                source, app)

    def test_the_mining_bot_is_excluded_because_it_genuinely_lacks_the_field(self):
        """Guards the exclusion itself: `eve-online-mining-bot` must really
        lack `numJumps`, not merely be left out for convenience."""
        source = source_of(parser_file("eve-online-mining-bot"))
        block = marker_type_alias_block(source)
        self.assertNotIn("numJumps", block)
