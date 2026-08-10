"""Tests for saxrat jumping the route's next stargate from the Selected Item
panel rather than by right-clicking the route panel's marker.

This is PR #170's rule ported from the mission runner, and what makes it worth
having here is the *share* rather than the per-leg saving. `routeMarkerCascade`
is the same cascade in both bots, with the same 200 tolerance and the same
comment about `"Jump Through Stargate"` taking 3-4 menu opens -- but counted in
**readings**, saxrat's run 13 spent 400 of its 1,706 readings inside it across 27
jump legs and run 14 348 of 910 across 26, a median of 12 and 13 readings a leg.
The mission runner's runs 35 and 37 answer 3 and 2 on the same measurement, and
2% and 3% of their readings. `TheCorpusTest` recounts all of that as relations.

**The identity condition is the whole safety of this change**, and most of these
cases are about it. A jump to the wrong gate is a wrong system, not a wasted
tick. `InfoPanelRouteRouteElementMarker` carries a `uiNode` and no name, so the
marker cannot say which gate it is; what answers is two other things the client
renders, the second of them read off this account's live client while this was
written, with that gate selected:

    route panel:  <a href="showinfo:5//30005001" alt="Next System in Route">Arnon</a>
    overview row: Name "Tar"   Type "Stargate (CONCORD System)"
    panel label:  Tar (<color=#ff4ecef8>0.8</color>)

That third line is the reading PR #170 shipped as unverified -- no capture of the
Selected Item panel with a *stargate* selected had ever recorded its texts, only
its buttons. `ThePanelNamesTheGateTest` runs it through the real parser and
`selectedItemIsOverviewEntry`, so the premise this branch fires on is executed
rather than assumed.

`TheRuleTest` asks the shipped rule for every answer it has, including the one
this feature exists to refuse: **the panel showing a different gate while the
jump button is offered.**

**The warp half is deliberately not ported**, and `TheWarpHalfIsNotServableTest`
pins that rather than leaving it to be rediscovered. saxrat's anomaly warp
cascades on a probe-scanner *scan result* -- a row in the scanner window, not an
object in space that the panel can be showing -- and picks a warp *distance*
through a two-level menu from the `warp-at` setting, which the panel's single
`selectedItemWarpTo` cannot express.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, and the readings they are asked about go through the real
`EveOnline.ParseUserInterface`. The wiring and the placement, which are not
expressions, are read out of the source through a reader sliced by
**indentation**: the `let_binding` shape ends at the next ` <name> = ` and stops
at a record literal, and `jumpThroughRouteStargate`'s `verdict` binding is one
big record.

Nothing here reads a live game client or drives a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl, recorded_runs
from test_saxrat_gate_panel_button import saxrat_runs
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, label,
    node, overview, source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The button, read off a live client with a stargate selected. The panel's set is
# object-specific: an acceleration gate draws `selectedItemActivateGate` and no
# jump at all, which is what made #167 look unbuildable for two of its comments.
JUMP_BUTTON = "selectedItemJump"

# The route panel's own label, in both the quote styles this repo has seen: the
# first read off the live macOS client, the second out of the 2019 recording in
# explore/2019-05-14.eve-online-bot-framework.
NEXT_SYSTEM_LABEL_LIVE = (
    '<center><a href="showinfo:5//30005001" alt="Next System in Route">Arnon'
    '</a></b> <hint="Security status">0.8</hint>')
NEXT_SYSTEM_LABEL_2019 = (
    "<center><url=showinfo:5//30001391 alt='Next System in Route'>Piekura"
    "</url></b> <color=0xffffff00L><hint='Security status'>0.5</hint></color>")

# The same panel's *other* label. It names a system too, and reading it as the
# next hop would jump towards the far end of the route rather than the next
# system.
DESTINATION_LABEL_2019 = (
    "<center><url=showinfo:5//30001367 alt='Current Destination'>Hageken"
    "</url></b>")

# Stargate rows as this client renders them, read live off the overview while the
# panel below was showing the first of them: the destination system alone in the
# Name column, the word in the Type column, and the region riding along in the
# type.
LIVE_STARGATE_ROWS = [
    ("Tar", "Stargate (CONCORD System)"),
    ("Emsar", "Stargate (CONCORD System)"),
    ("Kemerk", "Stargate (CONCORD System)"),
    ("Ourapheh", "Stargate (CONCORD System)"),
    ("Tolle", "Stargate (Gallente Border)"),
]

# What the Selected Item panel's `nameLabel` read on the same live reading, with
# the `Tar` gate selected. This is the text PR #170 could not record.
LIVE_PANEL_NAME_LABEL = "Tar (<color=#ff4ecef8>0.8</color>)"

# What the route cascade prints, per rung. `route element icon` is the only one of
# the three that names this cascade rather than the shared machinery, so an
# episode has to contain one before the other two count towards it.
CASCADE_OPEN = "Open context menu on route element icon"
CASCADE_CLICK = "first available of 'dock', 'jump'"
CASCADE_WAIT = "No context menu in this reading yet, but we right-clicked"

# Readings without cascade activity that still count as one leg rather than a gap
# between two. A jump leg's rungs sit within a few readings of each other; the
# next leg is a whole warp and a system change away.
EPISODE_GAP_READINGS = 10

READING_HEADER = re.compile(r"^# \[(\d+)\.(\d+)\] ")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)


def saxrat_source():
    return source_of(SAXRAT_BOT_ELM)


def doc_comment(name, path=SAXRAT_BOT_ELM):
    """The `{-| … -}` block immediately above a declaration's annotation.

    Read separately because `body_of` starts at the type annotation, and the
    measurement `TheCorpusTest` recomputes is quoted in the prose.
    """
    source = source_of(path)
    annotation = source.index("\n%s :" % name)
    opened = source.rindex("{-|", 0, annotation)
    closed = source.index("-}", opened)
    return collapsed(source[opened:closed])


def without_comments(text):
    """The same source with its `--` lines and its `{-| … -}` blocks dropped.

    Any case asserting something is *absent* needs both. `collapsed` puts a line
    comment on the same line as the code, and the doc comments here quote the
    very expressions the counting cases below look for -- this file's own
    `overviewEntryIsAStargate` comment names `containsWords "stargate"` while
    arguing for there being one of it.
    """
    without_docs = re.sub(r"\{-\|.*?-\}", "", text, flags=re.DOTALL)
    return "\n".join(
        line for line in without_docs.splitlines()
        if not line.strip().startswith("--"))


def indented_binding(declaration_name, name, path=SAXRAT_BOT_ELM):
    """One `let` binding, sliced by indentation rather than by the next `=`.

    Ends at the next non-blank line indented no further than the binding's own
    name. A reader that ends at the next ` <name> = ` stops at a **record
    literal**, and `jumpThroughRouteStargate`'s `verdict` binding is one big
    record -- so an assertion about what it is handed would read text that
    stopped at the opening brace and pass having checked nothing.
    """
    lines = body_of(source_of(path), declaration_name).splitlines()
    opens = [index for index, line in enumerate(lines)
             if re.match(r"^\s*%s\s*=" % re.escape(name), line)]
    assert opens, "no let binding named %r in %r" % (name, declaration_name)
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            end = index
            break
    return collapsed(without_comments("\n".join(lines[start:end])))


def route_panel(label_texts):
    """An `InfoPanelContainer` holding an `InfoPanelRoute` with these labels.

    Built for the real parser rather than by hand: `parseInfoPanelRouteFrom
    InfoPanelContainer` finds the route panel by type name among the container's
    descendants, and every node it navigates needs a display region.
    """
    return node("InfoPanelContainer", {}, [
        node("InfoPanelRoute", {}, [
            label(text, (0, index * 16, 200, 16))
            for index, text in enumerate(label_texts)
        ], region=(0, 0, 200, 64)),
    ], region=(0, 0, 200, 64))


def selected_item_window(showing, buttons=()):
    """The Selected Item panel, as the real parser will accept it.

    The macOS client calls this window `SelectedItemWnd`, and everything the bot
    reads off it afterwards is a descendant: the name it is showing as display
    text, and each action button by its own `_name`.
    """
    children = [node("EveLabelMedium",
                     {"_name": "nameLabel", "_setText": showing},
                     region=(0, 0, 200, 16))]
    for index, name in enumerate(buttons):
        children.append(
            node("SelectedItemButton", {"_name": name},
                 region=(index * 34, 20, 32, 32)))
    return node("SelectedItemWnd", {}, children, region=(0, 600, 200, 80))


class JumpRepl(SaxratRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-jump-repl-")
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


def readings_with_decisions(path):
    """Every reading in a run log, as the decision lines printed inside it.

    Keyed on the integer part of `# [tick.substep]`, which is the reading the
    framework was working from -- several framework steps share one, and counting
    steps or lines instead is how a six-minute stall was once written up as an
    all-session one.
    """
    order = []
    decisions = {}
    current = None
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            header = READING_HEADER.match(line)
            if header:
                current = int(header.group(1))
                if current not in decisions:
                    decisions[current] = []
                    order.append(current)
            elif line.startswith("+") and current is not None:
                decisions[current].append(line.rstrip("\n"))
    return [decisions[index] for index in order]


def cascade_episodes(readings):
    """The route cascade's readings, grouped into one group per jump leg.

    A leg is a contiguous run of readings carrying any of the cascade's three
    rungs, allowing `EPISODE_GAP_READINGS` between two of them. Groups holding no
    `route element icon` line are dropped: the wait rung is shared machinery and
    appears under other cascades too.
    """
    marks = [(any(CASCADE_OPEN in line for line in decisions),
              any(rung in line
                  for line in decisions
                  for rung in (CASCADE_OPEN, CASCADE_CLICK, CASCADE_WAIT)))
             for decisions in readings]

    episodes = []
    index = 0
    while index < len(marks):
        if not marks[index][1]:
            index += 1
            continue
        start = last = index
        probe = index + 1
        while probe < len(marks) and probe - last <= EPISODE_GAP_READINGS:
            if marks[probe][1]:
                last = probe
            probe += 1
        group = [position for position in range(start, last + 1)
                 if marks[position][1]]
        if any(marks[position][0] for position in group):
            episodes.append(group)
        index = last + 1
    return episodes


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


class TheRuleTest(unittest.TestCase):
    """`routeStargateJump`, executed at each of its six answers.

    Every case asks all six equalities rather than the one it expects, so a rule
    that answers two things at once -- or none -- fails rather than passing on
    whichever constructor the case happened to name.
    """

    repl = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(JumpRepl)

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()

    def answers(self, next_system, gates, offers_jump):
        """The six equalities, in the order `expect` names them."""
        rendered_gates = ", ".join(
            '{ name = "%s", panelIsShowingIt = %s }'
            % (name, "True" if showing else "False")
            for name, showing in gates)
        given = (
            'routeStargateJump { nextSystemOnRoute = %s,'
            ' stargatesOnOverview = [ %s ], panelOffersJump = %s }'
            % ('Nothing' if next_system is None else 'Just "%s"' % next_system,
               rendered_gates,
               "True" if offers_jump else "False"))
        return self.repl.evaluate([
            "(%s) == PressTheJumpButton %s" % (given, self._press_argument(gates)),
            "(%s) == NoNextSystemOnRoute" % given,
            '(%s) == NoStargateNamedForTheNextSystem "%s"' % (given, next_system),
            '(%s) == SeveralStargatesNamedForTheNextSystem "%s"' % (given, next_system),
            '(%s) == ThePanelIsShowingSomethingElse "%s"' % (given, next_system),
            '(%s) == ThePanelOffersNoJump "%s"' % (given, next_system),
        ])

    @staticmethod
    def _press_argument(gates):
        """The gate name a press would carry, or a name no row has."""
        return '"%s"' % (gates[0][0] if gates else "no gate at all")

    def expect(self, which, next_system, gates, offers_jump):
        names = ["press", "no next system", "no gate named", "several gates",
                 "panel showing something else", "no jump button"]
        answers = self.answers(next_system, gates, offers_jump)
        self.assertEqual(
            [name for name, answer in zip(names, answers) if answer], [which],
            "the rule answered %s"
            % [name for name, answer in zip(names, answers) if answer])

    def test_the_button_is_pressed_when_the_panel_shows_the_route_s_gate(self):
        self.expect("press", "Tar", [("Tar", True)], True)

    def test_a_panel_showing_a_different_gate_does_not_jump(self):
        """The failure this whole design refuses.

        The button is offered and the gate for the next system is on the
        overview -- but the panel is showing something else, so pressing Jump
        acts on whatever that is. It falls back rather than selecting the row
        first, because selecting spends the reading this exists to save.
        """
        self.expect("panel showing something else", "Tar",
                    [("Tar", False)], True)

    def test_no_named_next_system_declines(self):
        self.expect("no next system", None, [("Tar", True)], True)

    def test_no_gate_named_for_the_next_system_declines(self):
        self.expect("no gate named", "Tar", [("Tolle", True)], True)

    def test_two_gates_named_for_one_system_decline(self):
        """A system's name is unique, so two rows naming it is not a choice this
        reading can make."""
        self.expect("several gates", "Tar",
                    [("Tar", True), ("Tar", False)], True)

    def test_no_jump_button_declines(self):
        self.expect("no jump button", "Tar", [("Tar", True)], False)

    def test_an_empty_overview_declines(self):
        self.expect("no gate named", "Tar", [], True)

    def test_the_rule_reads_nothing_but_its_own_record(self):
        """It takes three named fields and reaches for no reading and no context,
        which is what lets every case above execute it."""
        body = collapsed(without_comments(
            body_of(saxrat_source(), "routeStargateJump")))
        for forbidden in ("readingFromGameClient", "BotDecisionContext",
                          "context.memory", "overviewWindows"):
            self.assertNotIn(forbidden, body)


class TheGateNameMatchTest(unittest.TestCase):
    """`stargateNameLeadsToSystem`, over the rows the client really draws."""

    repl = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(JumpRepl)

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()

    def matches(self, pairs):
        return self.repl.evaluate([
            'stargateNameLeadsToSystem "%s" "%s"' % (system, gate)
            for system, gate in pairs])

    def test_the_live_rows_match_their_own_systems(self):
        self.assertEqual(
            self.matches([(name, name) for name, _ in LIVE_STARGATE_ROWS]),
            [True] * len(LIVE_STARGATE_ROWS))

    def test_the_live_rows_do_not_match_each_other(self):
        names = [name for name, _ in LIVE_STARGATE_ROWS]
        pairs = [(one, other) for one in names for other in names
                 if one != other]
        self.assertEqual(self.matches(pairs), [False] * len(pairs))

    def test_only_the_row_s_name_is_matched_against_the_route_s_system(self):
        """A type reads `Stargate (Amarr Border)` and Amarr is a real system, so
        a rule reading both columns matches a gate leading somewhere else."""
        self.assertEqual(
            self.matches([("Amarr", "Stargate (Amarr Border)")]), [True],
            "the type text does match by itself, which is why the rule is only "
            "ever handed the Name column")
        wiring = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn("name = gate.objectName", wiring)
        self.assertNotIn("objectType", wiring)

    def test_a_parenthesised_row_name_still_matches(self):
        """An overview preset can render `Stargate (Tar)` in the Name column."""
        self.assertEqual(
            self.matches([("Tar", "Stargate (Tar)"),
                          ("Tar", "Tar - Stargate"),
                          ("Tar", "[Tar]")]),
            [True, True, True])

    def test_a_system_name_is_not_matched_as_a_substring(self):
        self.assertEqual(
            self.matches([("Ami", "Amir"), ("Tar", "Tartarus"),
                          ("Tar", "Stargate (Tarta)")]),
            [False, False, False])

    def test_a_hyphenated_system_name_matches_itself(self):
        self.assertEqual(self.matches([("1DQ1-A", "1DQ1-A")]), [True])

    def test_a_hyphenated_system_does_not_match_its_neighbour(self):
        self.assertEqual(
            self.matches([("1DQ1-A", "1DQ1-B"), ("1DQ1-A", "1DQ1")]),
            [False, False])

    def test_the_case_the_client_writes_is_not_load_bearing(self):
        self.assertEqual(self.matches([("tar", "TAR")]), [True])


class TheNextSystemLabelTest(unittest.TestCase):
    """`nextSystemOnRouteFromReading`, over the client's own markup."""

    repl = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(JumpRepl)

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()

    def parsed(self, labels):
        """What the rule answers for a reading whose route panel holds `labels`.

        Through the real parser, so what is asserted is what the bot would have
        been handed rather than a record shaped by hand.
        """
        definition = self.repl.reading_binding("reading", [route_panel(labels)])
        return self.repl.strings(
            ['reading |> Maybe.andThen nextSystemOnRouteFromReading'
             ' |> Maybe.withDefault "nothing"'],
            definitions=[definition])[0]

    def test_the_live_client_s_label_names_the_next_system(self):
        self.assertEqual(self.parsed([NEXT_SYSTEM_LABEL_LIVE]), "Arnon")

    def test_the_2019_recording_s_label_names_it_too(self):
        """The other quote style, which `parseCurrentSolarSystemFromUINodeText`
        already handles for its own label."""
        self.assertEqual(self.parsed([NEXT_SYSTEM_LABEL_2019]), "Piekura")

    def test_the_destination_label_is_not_read_as_the_next_system(self):
        """The panel names two systems and only one of them is the next hop."""
        self.assertEqual(self.parsed([DESTINATION_LABEL_2019]), "nothing")

    def test_the_next_system_is_taken_from_a_panel_carrying_both(self):
        self.assertEqual(
            self.parsed([DESTINATION_LABEL_2019, NEXT_SYSTEM_LABEL_2019]),
            "Piekura")

    def test_a_label_with_no_marker_answers_nothing(self):
        self.assertEqual(self.parsed(["Route <fontsize=12></b>3 Jumps"]),
                         "nothing")

    def test_an_empty_name_answers_nothing(self):
        """A blank name would match every gate on the overview."""
        self.assertEqual(
            self.parsed(['<center><a href="showinfo:5//1" '
                         'alt="Next System in Route"> </a>']),
            "nothing")

    def test_a_reading_with_no_route_panel_answers_nothing(self):
        definition = self.repl.reading_binding("reading", [overview([])])
        self.assertEqual(
            self.repl.strings(
                ['reading |> Maybe.andThen nextSystemOnRouteFromReading'
                 ' |> Maybe.withDefault "nothing"'],
                definitions=[definition])[0],
            "nothing")

    def test_the_marker_is_the_client_s_own_wording(self):
        body = collapsed(body_of(saxrat_source(),
                                 "parseNextSystemInRouteFromLabelText"))
        self.assertIn("alt='Next System in Route'", body)
        self.assertIn('alt=\\"Next System in Route\\"', body)


class ThePanelNamesTheGateTest(unittest.TestCase):
    """The premise PR #170 shipped as unverified, read off the live client.

    That PR could not record what the Selected Item panel *says* with a stargate
    selected -- only which buttons it draws -- so the branch rested on
    `selectedItemIsOverviewEntry` matching something nobody had seen. It was read
    here: with the `Tar` gate selected, the panel's `nameLabel` carries the
    system's name and its security status, and the overview row for the same gate
    carries the system's name alone.
    """

    repl = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(JumpRepl)

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()

    def showing(self, panel_text, row_names):
        """Whether the panel reads as showing each named row, through the parser."""
        rows = [("8,998 m", name, "Stargate (CONCORD System)")
                for name in row_names]
        definition = self.repl.reading_binding("reading", [
            overview(rows),
            selected_item_window(panel_text, [JUMP_BUTTON]),
        ])
        return self.repl.evaluate([
            'reading |> Maybe.map (\\r -> r.overviewWindows'
            ' |> List.concatMap .entries |> List.drop %d |> List.head'
            ' |> Maybe.map (selectedItemIsOverviewEntry r)'
            ' |> Maybe.withDefault False) |> Maybe.withDefault False' % index
            for index in range(len(row_names))
        ], definitions=[definition])

    def test_the_live_panel_reads_as_showing_the_live_row(self):
        self.assertEqual(self.showing(LIVE_PANEL_NAME_LABEL, ["Tar"]), [True])

    def test_the_live_panel_does_not_read_as_showing_the_other_gates(self):
        others = [name for name, _ in LIVE_STARGATE_ROWS if name != "Tar"]
        self.assertEqual(self.showing(LIVE_PANEL_NAME_LABEL, others),
                         [False] * len(others))

    def test_the_live_rows_read_as_stargates(self):
        definition = self.repl.reading_binding("reading", [
            overview([("8,998 m", name, object_type)
                      for name, object_type in LIVE_STARGATE_ROWS]),
        ])
        self.assertEqual(
            self.repl.evaluate([
                'reading |> Maybe.map (\\r -> r.overviewWindows'
                ' |> List.concatMap .entries'
                ' |> List.all overviewEntryIsAStargate)'
                ' |> Maybe.withDefault False'],
                definitions=[definition]),
            [True])

    def test_a_row_that_is_not_a_stargate_is_declined(self):
        definition = self.repl.reading_binding("reading", [
            overview([("2 m", "Beacon", "Beacon"),
                      ("1,600 m", "Naglfar Wreck", "Naglfar Wreck")]),
        ])
        self.assertEqual(
            self.repl.evaluate([
                'reading |> Maybe.map (\\r -> r.overviewWindows'
                ' |> List.concatMap .entries'
                ' |> List.any overviewEntryIsAStargate)'
                ' |> Maybe.withDefault True'],
                definitions=[definition]),
            [False])

    def test_the_stargate_test_reads_both_columns(self):
        """Which column carries the word is a matter of overview preset, unlike
        the identity match, which is only ever handed the Name."""
        body = collapsed(without_comments(
            body_of(saxrat_source(), "overviewEntryIsAStargate")))
        self.assertIn("entry.objectName", body)
        self.assertIn("entry.objectType", body)


class TheWordingTest(unittest.TestCase):
    """`describeRouteStargateJump`, rendered rather than asserted by substring.

    A case that asserts a name appears somewhere in the branch can pass on the
    branch's own log text quoting it, which is how a mutation aimed at the wrong
    button once survived in `test_saxrat_gate_panel_button`.
    """

    repl = None
    rendered = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(JumpRepl)
        cls.rendered = dict(zip(
            ["press", "no next system", "no gate named", "several gates",
             "panel showing something else", "no jump button"],
            cls.repl.strings([
                'describeRouteStargateJump (PressTheJumpButton "Tar")',
                'describeRouteStargateJump NoNextSystemOnRoute',
                'describeRouteStargateJump (NoStargateNamedForTheNextSystem "Tar")',
                'describeRouteStargateJump (SeveralStargatesNamedForTheNextSystem "Tar")',
                'describeRouteStargateJump (ThePanelIsShowingSomethingElse "Tar")',
                'describeRouteStargateJump (ThePanelOffersNoJump "Tar")',
            ])))

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()

    def test_every_answer_reads_differently(self):
        self.assertEqual(len(set(self.rendered.values())),
                         len(self.rendered))

    def test_the_press_names_the_gate_and_says_the_panel_already_showed_it(self):
        press = self.rendered["press"]
        self.assertIn("'Tar'", press)
        self.assertIn("already showing it", press)

    def test_every_fall_back_names_the_route_marker(self):
        """An operator reading a stretch of these has to see the cascade is still
        travelling the route rather than that the jump has stopped happening."""
        for which, text in self.rendered.items():
            if which == "press":
                continue
            self.assertIn("route marker", text, which)

    def test_no_fall_back_reads_as_a_press(self):
        for which, text in self.rendered.items():
            if which == "press":
                continue
            self.assertNotIn("already showing it", text, which)

    def test_the_ones_that_know_a_system_name_it(self):
        for which in ("no gate named", "several gates",
                      "panel showing something else", "no jump button"):
            self.assertIn("'Tar'", self.rendered[which], which)

    def test_the_showing_something_else_sentence_says_what_selecting_costs(self):
        self.assertIn("spend the reading",
                      self.rendered["panel showing something else"])

    def test_the_system_named_is_the_one_it_was_given(self):
        other = self.repl.strings([
            'describeRouteStargateJump (NoStargateNamedForTheNextSystem "Emsar")'
        ])[0]
        self.assertIn("'Emsar'", other)
        self.assertNotIn("Tar", other)


class TheWiringTest(unittest.TestCase):
    """What the branch is handed and where it sits, read out of the source."""

    def setUp(self):
        self.source = saxrat_source()
        self.jump_leg = collapsed(without_comments(
            body_of(self.source, "jumpToNextSystem")))
        self.branch = collapsed(without_comments(
            body_of(self.source, "jumpThroughRouteStargate")))

    def test_the_travel_leg_tries_the_panel_before_the_route_marker(self):
        self.assertIn("jumpThroughRouteStargate context", self.jump_leg)
        self.assertLess(
            self.jump_leg.index("jumpThroughRouteStargate"),
            self.jump_leg.index("useContextMenuCascadeWithCustomConfig"))

    def test_the_panel_path_is_inside_the_drone_recall(self):
        """A jump leaves whatever is in space behind, panel press or menu entry."""
        self.assertLess(
            self.jump_leg.index("returnDronesToBay context"),
            self.jump_leg.index("jumpThroughRouteStargate"))

    def test_the_panel_path_is_behind_the_settling_guard(self):
        """During the recompute window the label can still name the previous
        route's next system, which is the wrong system this refuses everywhere
        else."""
        self.assertLess(
            self.jump_leg.index("routeFirstMarkerUnchangedTicks"),
            self.jump_leg.index("jumpThroughRouteStargate"))

    def test_the_gates_offered_to_the_rule_are_rendered_stargates(self):
        wiring = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn("overviewEntryIsDisplayed", wiring)
        self.assertIn("overviewEntryIsAStargate", wiring)

    def test_each_gate_carries_whether_the_panel_is_showing_that_gate(self):
        """Per row, not once for the whole overview -- a single answer computed
        outside the map would report the same thing about every gate."""
        wiring = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn("panelIsShowingIt", wiring)
        self.assertIn("selectedItemIsOverviewEntry context.readingFromGameClient gate",
                      wiring)

    def test_the_next_system_comes_from_the_route_panel(self):
        wiring = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn(
            "nextSystemOnRoute = nextSystemOnRouteFromReading"
            " context.readingFromGameClient", wiring)

    def test_the_rule_is_told_whether_the_button_is_really_there(self):
        """The rule's `panelOffersJump` is the lookup, not a constant.

        `test_no_jump_button_declines` asks the rule directly, so it cannot see
        this: a wiring that always says the button is there leaves the rule
        answering `PressTheJumpButton` while the tuple match below still falls
        back, and the decision log then claims a press on every reading the
        panel offers nothing. That is exactly the two-places-disagreeing failure
        `describeRouteStargateJump` is derived from the verdict to avoid, and it
        survived the first mutation pass.
        """
        wiring = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn("panelOffersJump = jumpButton /= Nothing", wiring)

    def test_the_button_offered_is_the_button_pressed(self):
        """The lookup and the press are the same value, so a press cannot land on
        a button the rule was not told about."""
        lookup = indented_binding("jumpThroughRouteStargate", "jumpButton")
        self.assertIn('selectedItemButtonNamed context.readingFromGameClient "%s"'
                      % JUMP_BUTTON, lookup)
        self.assertIn("( PressTheJumpButton _, Just buttonToPress ) -> describeBranch"
                      " (describeRouteStargateJump verdict)"
                      " (clickUiElement buttonToPress)", self.branch)

    def test_it_never_selects_a_row_first(self):
        """The one departure from the acceleration gate's select-then-press
        shape: selecting spends the reading this exists to save."""
        for forbidden in ("clickUiElement gate", "clickUiElement accelerationGate",
                          "SelectTheGate"):
            self.assertNotIn(forbidden, self.branch)

    def test_the_fall_back_hands_the_caller_s_own_step_back(self):
        self.assertIn("ifThePanelCannotDoIt", self.branch)
        self.assertNotIn("waitForProgressInGame", self.branch)
        self.assertNotIn("askForHelpToGetUnstuck", self.branch)

    def test_both_branches_say_which_answer_they_took(self):
        self.assertEqual(
            self.branch.count("describeBranch (describeRouteStargateJump verdict)"),
            2)

    def test_the_route_marker_cascade_is_otherwise_unchanged(self):
        """The tolerance is why this cascade is worth replacing readings of, and
        the fall-back is still what travels every leg the panel cannot identify."""
        self.assertIn("discardContextMenuIfTooDistantFromTargetElement"
                      " { toleratedDistance = 200 }", self.jump_leg)
        self.assertIn('targetUIElementName = "route element icon"', self.jump_leg)
        self.assertIn('[ "dock" , "jump" ]', self.jump_leg)

    def test_the_stargate_predicate_has_one_definition(self):
        """Two copies of "is this a stargate" would drift silently in both
        directions, and this one decides which object a jump command acts on."""
        self.assertEqual(
            len(re.findall(r"^overviewEntryIsAStargate :", self.source,
                           re.MULTILINE)), 1)
        self.assertEqual(
            len(re.findall(r'containsWords "stargate"',
                           without_comments(self.source))), 1)


class TheWarpHalfIsNotServableTest(unittest.TestCase):
    """Why the anomaly warp is not ported alongside the jump.

    The Selected Item panel acts on the object that is *selected in space*.
    saxrat's anomaly warp acts on a probe-scanner scan result, which is a row in
    the scanner window and has no overview entry for the panel to be showing; and
    it chooses a warp *distance* through a two-level menu, which the panel's
    single `selectedItemWarpTo` cannot express. Both halves are pinned here so a
    later port has to argue against them rather than rediscover them.
    """

    def setUp(self):
        self.source = saxrat_source()
        self.enter_anomaly = collapsed(without_comments(
            body_of(self.source, "enterAnomaly")))

    def test_the_warp_acts_on_a_scan_result_rather_than_an_object_in_space(self):
        self.assertIn("probeScannerWindow", self.enter_anomaly)
        self.assertIn('( "Scan result", anomalyScanResult.uiNode )',
                      self.enter_anomaly)

    def test_the_warp_chooses_a_distance_through_a_two_level_menu(self):
        """`warp-at` picks the range, and the panel button carries no argument."""
        self.assertIn('useMenuEntryWithTextContaining "to within"',
                      self.enter_anomaly)
        self.assertIn("botSettings.warpAt", self.enter_anomaly)

    def test_the_warp_is_not_wired_to_the_panel(self):
        for forbidden in ("selectedItemWarpTo", "selectedItemButtonNamed",
                          "selectedItemIsOverviewEntry"):
            self.assertNotIn(forbidden, self.enter_anomaly)

    def test_the_panel_is_only_ever_asked_about_overview_rows(self):
        """`selectedItemIsOverviewEntry` takes an `OverviewWindowEntry`, so a
        scan result cannot be handed to it without a change of type."""
        signature = collapsed(
            body_of(self.source, "selectedItemIsOverviewEntry"))
        self.assertIn("EveOnline.ParseUserInterface.OverviewWindowEntry",
                      signature)

    def test_the_panel_press_this_change_adds_is_the_only_new_one(self):
        """Two panel presses in the file now -- the acceleration gate's and this
        one -- and nothing else has started reaching for a panel button."""
        self.assertEqual(
            len(re.findall(r"selectedItemButtonNamed context\.",
                           without_comments(self.source))), 2)


class TheCorpusTest(unittest.TestCase):
    """What saxrat's own runs say the cascade costs, and what the mission
    runner's say it costs there.

    Counted in readings rather than decision lines. The bot re-derives its whole
    decision path on every framework event, so a leg that prints twenty decision
    lines is a dozen or so readings -- and counting the other way is how this repo
    has twice mis-calibrated a threshold.

    Recounted as *relations* rather than as the numbers the doc comment quotes,
    except for the doc comment's own check, so a corpus that grows cannot turn a
    true claim red.
    """

    def episodes_by_run(self):
        found = []
        for path in saxrat_runs(13, 14):
            readings = readings_with_decisions(path)
            found.append((os.path.basename(path), readings,
                          cascade_episodes(readings)))
        return [entry for entry in found if entry[2]]

    def test_the_cascade_costs_many_readings_on_a_jump_leg(self):
        for name, _, episodes in self.episodes_by_run():
            spent = sum(len(episode) for episode in episodes)
            self.assertGreater(
                spent, 4 * len(episodes),
                "%s: %d readings across %d legs" % (name, spent, len(episodes)))

    def test_the_median_leg_is_expensive_rather_than_a_tail(self):
        """The doc comment argues on the median, not on the worst leg, so the
        median has to be the thing that is large."""
        for name, _, episodes in self.episodes_by_run():
            self.assertGreaterEqual(
                median([len(episode) for episode in episodes]), 8, name)

    def test_the_cascade_holds_a_large_share_of_every_reading_in_the_run(self):
        """The share is what makes this worth doing on saxrat, where on the
        mission runner the per-leg saving was one to two readings."""
        for name, readings, episodes in self.episodes_by_run():
            spent = sum(len(episode) for episode in episodes)
            self.assertGreater(
                spent, len(readings) // 10,
                "%s: %d of %d readings" % (name, spent, len(readings)))

    def test_the_mission_runner_s_legs_are_much_cheaper_than_saxrat_s(self):
        """The comparison the doc comment rests on. Both bots are measured the
        same way, off the same rung wordings, in the same unit."""
        mission = []
        for _, path in recorded_runs("35", "37"):
            readings = readings_with_decisions(path)
            episodes = cascade_episodes(readings)
            if episodes:
                mission.append((readings, episodes))
        self.assertTrue(mission, "no route cascade in the mission runner's runs")

        saxrat = self.episodes_by_run()
        worst_mission_median = max(
            median([len(episode) for episode in episodes])
            for _, episodes in mission)
        best_saxrat_median = min(
            median([len(episode) for episode in episodes])
            for _, _, episodes in saxrat)
        self.assertGreater(best_saxrat_median, 2 * worst_mission_median)

        biggest_mission_share = max(
            sum(len(episode) for episode in episodes) / len(readings)
            for readings, episodes in mission)
        smallest_saxrat_share = min(
            sum(len(episode) for episode in episodes) / len(readings)
            for _, readings, episodes in saxrat)
        self.assertGreater(smallest_saxrat_share, 3 * biggest_mission_share)

    def test_the_doc_comment_s_counts_are_what_the_runs_hold(self):
        """A claim the corpus stops supporting goes red rather than standing."""
        comment = doc_comment("jumpThroughRouteStargate")
        quoted = dict(
            (int(run), (int(readings), int(legs)))
            for run, readings, legs in re.findall(
                r"run (\d+) \*\*(\d+) (?:readings )?across (\d+)"
                r"(?: jump legs)?\*\*", comment))
        self.assertTrue(quoted, "the doc comment quotes no counts: %s" % comment)

        for name, _, episodes in self.episodes_by_run():
            number = int(re.search(r"saxrat_run(\d+)", name).group(1))
            if number not in quoted:
                continue
            self.assertEqual(
                (sum(len(episode) for episode in episodes), len(episodes)),
                quoted[number], name)

    def test_the_panel_path_would_have_had_something_to_identify(self):
        """Every recorded jump leg is one the bot was standing in space for, with
        the overview it would have had to read the gate off."""
        for name, readings, episodes in self.episodes_by_run():
            in_space = [index for episode in episodes for index in episode
                        if any("scan results" in line
                               for line in readings[index])]
            self.assertGreater(
                len(in_space),
                sum(len(episode) for episode in episodes) // 2, name)


if __name__ == "__main__":
    unittest.main()
