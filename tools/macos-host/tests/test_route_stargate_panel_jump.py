"""Tests for jumping the route's next stargate from the Selected Item panel.

Ordinary gate-to-gate travel goes through `routeMarkerCascade`, which right-
clicks the route panel's 8x8 marker and takes the menu's `Jump Through
Stargate`. It is the worst-behaved cascade in the codebase and carries a
distance tolerance of its own, widened to 200 because "'Jump Through Stargate'
took 3-4 menu opens before being recognized" against an icon in a strip that
shifts as the route updates. `selectedItemJump` is the one-click alternative,
read live off a client with a **stargate** selected:

    selectedItemApproach    selectedItemJump       selectedItemKeepAtRange
    selectedItemLockTarget  selectedItemOrbit      selectedItemResetCamera
    selectedItemSetInterest selectedItemShowInfo   selectedItemWarpTo

**The identity condition is the whole safety of this change, and it is what
most of these cases are about.** A jump to the wrong gate is a wrong system,
not a wasted tick. `dockAtDestinationStation` shipped assuming one route marker
meant the nearest station was the destination; #98 was the regression, and
nothing had checked identity at all. `InfoPanelRouteRouteElementMarker` carries
a `uiNode` and no name, so the marker itself cannot say which gate it is --
what answers is two other things the client renders, both read off the live
client while this was written:

    route panel:  <a href="showinfo:5//30005001" alt="Next System in Route">Arnon</a>
    overview row: Name "Adirain"   Type "Stargate (Gallente System)"

so the match is between the system the route names next and the system a gate's
own row says it leads to. `TheRuleTest` asks the shipped rule for every answer
it has, including the one this feature exists to refuse: **the panel showing a
different gate while the jump button is offered.**

**The saving is small and is measured rather than asserted.**
`TheCorpusTest` recounts the cascade out of `~/eve-bot-logs` in *readings*
rather than decision lines -- CLAUDE.md's own first orientation note -- and
checks the numbers `jumpThroughRouteStargate`'s doc comment quotes against what
the runs actually hold, so a doc comment claiming a saving the corpus does not
show goes red.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python. The wiring and the placement, which are not expressions,
are read out of the source through readers sliced by **indentation**: the
`let_binding` shape that ends at the next ` <name> = ` stops at a record
literal, and `jumpThroughRouteStargate`'s bindings build one -- PRs #147, #156,
#159 and #162 all paid for that reader.

Nothing here reads a live game client or drives a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import MISSION_RUNNER_DIR, open_repl, recorded_runs

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The button, read off a live client with a stargate selected. The panel's set
# is object-specific: an acceleration gate in a mission pocket draws
# `selectedItemActivateGate` and no jump at all, which is what made #167 look
# unbuildable for two of its three comments.
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

# Stargate rows as this client renders them, read live: the destination system
# alone in the Name column, the word in the Type column, and the region's name
# riding along in the type.
LIVE_STARGATE_ROWS = [
    ("Adirain", "Stargate (Gallente System)"),
    ("Aere", "Stargate (Gallente System)"),
    ("Emsar", "Stargate (Gallente Border)"),
    ("Laurvier", "Stargate (Gallente System)"),
]

# What the cascade prints, per rung. `route element icon` is the only one of
# the three that names this cascade rather than the shared machinery, so an
# episode has to contain one before the other two count towards it.
CASCADE_OPEN = "Open context menu on route element icon"
CASCADE_CLICK = "first available of 'dock', 'jump'"
CASCADE_WAIT = (
    "No context menu in this reading yet, but we right-clicked")

# Readings without cascade activity that still count as one leg rather than a
# gap between two. A jump leg's rungs sit within a couple of readings of each
# other; the next leg is a whole warp and a system change away.
EPISODE_GAP_READINGS = 10

READING_HEADER = re.compile(r"^# \[(\d+)\.(\d+)\] ")


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """`text` with every run of whitespace flattened to one space.

    Source assertions go through this so the next `elm-format` pass cannot
    break them the way #58's broke three others.
    """
    return " ".join(text.split())


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Any case asserting something is *absent* needs this: `collapsed` puts a
    comment on the same line as the code, and a doc comment naming a branch
    deliberately left elsewhere would satisfy the assertion.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(name, source=None):
    """One top-level declaration, from its type annotation to the next one."""
    match = re.search(r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name),
                      source if source is not None else bot_elm(),
                      re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def doc_comment(name):
    """The `{-| … -}` block immediately above a declaration's annotation.

    Read separately because `declaration` starts at the type annotation, and
    the measurement `TheCorpusTest` recomputes is quoted in the prose.
    """
    source = bot_elm()
    annotation = source.index("\n%s :" % name)
    opened = source.rindex("{-|", 0, annotation)
    closed = source.index("-}", opened)
    return collapsed(source[opened:closed])


def indented_binding(declaration_name, name):
    """One `let` binding, sliced by indentation rather than by a blank line.

    Ends at the next non-blank line indented no further than the binding's own
    name. A reader that ends at the next ` <name> = ` stops at a **record
    literal**, and `jumpThroughRouteStargate`'s `verdict` binding is one big
    record -- so an assertion about what it is handed would read text that
    stopped at the opening brace and pass having checked nothing. PRs #147,
    #156, #159 and #162 each paid for that once.
    """
    lines = declaration(declaration_name).splitlines()
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


def readings_with_decisions(path):
    """Every reading in a run log, as the decision lines printed inside it.

    Keyed on the integer part of `# [tick.substep]`, which is the reading the
    framework was working from -- several framework steps share one, and
    counting steps or lines instead is how a six-minute stall was once written
    up as an all-session one.
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


def cascade_episodes(path):
    """The route cascade's readings, grouped into one group per jump leg.

    A leg is a contiguous run of readings carrying any of the cascade's three
    rungs, allowing `EPISODE_GAP_READINGS` between two of them. Groups holding
    no `route element icon` line are dropped: the wait rung is shared machinery
    and appears under other cascades too.
    """
    readings = readings_with_decisions(path)
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

    Asked as six equalities per case rather than one, so a rule that answered
    two things at once -- or none -- would fail rather than pass on whichever
    constructor a case happened to name.
    """

    NEXT_SYSTEM = "Adirain"
    GATE_NAME = "Adirain"

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def answers(self, next_system, gates, offers_jump):
        """The one constructor the rule answers with, by name."""
        expression = (
            "routeStargateJump { nextSystemOnRoute = %s"
            ", stargatesOnOverview = [ %s ], panelOffersJump = %s }" % (
                "Nothing" if next_system is None else 'Just "%s"' % next_system,
                ", ".join('{ name = "%s", panelIsShowingIt = %s }'
                          % (name, "True" if showing else "False")
                          for name, showing in gates),
                "True" if offers_jump else "False"))
        candidates = [
            ("PressTheJumpButton", 'PressTheJumpButton "%s"' % self.GATE_NAME),
            ("NoNextSystemOnRoute", "NoNextSystemOnRoute"),
            ("NoStargateNamedForTheNextSystem",
             'NoStargateNamedForTheNextSystem "%s"' % self.NEXT_SYSTEM),
            ("SeveralStargatesNamedForTheNextSystem",
             'SeveralStargatesNamedForTheNextSystem "%s"' % self.NEXT_SYSTEM),
            ("ThePanelIsShowingSomethingElse",
             'ThePanelIsShowingSomethingElse "%s"' % self.NEXT_SYSTEM),
            ("ThePanelOffersNoJump",
             'ThePanelOffersNoJump "%s"' % self.NEXT_SYSTEM),
        ]
        matched = [name for (name, value), yes in zip(
            candidates,
            self.repl.evaluate(["(%s) == %s" % (expression, value)
                                for _, value in candidates]))
            if yes]
        self.assertEqual(
            len(matched), 1,
            "expected exactly one answer for %s, got %s" % (expression, matched))
        return matched[0]

    def test_the_button_is_pressed_when_the_panel_shows_the_route_s_gate(self):
        self.assertEqual(
            self.answers("Adirain", [("Adirain", True)], True),
            "PressTheJumpButton")

    def test_a_panel_showing_a_different_gate_does_not_jump(self):
        """The case this whole feature is bounded by.

        Two gates on the grid, the panel showing the one the route does *not*
        want, and `selectedItemJump` offered because the panel is showing a
        stargate. Pressing it here is a jump into the wrong system, and every
        log line would read like success.
        """
        self.assertEqual(
            self.answers("Adirain", [("Adirain", False), ("Aere", True)], True),
            "ThePanelIsShowingSomethingElse")

    def test_no_named_next_system_declines(self):
        self.assertEqual(
            self.answers(None, [("Adirain", True)], True),
            "NoNextSystemOnRoute")

    def test_no_gate_named_for_the_next_system_declines(self):
        self.assertEqual(
            self.answers("Adirain", [("Aere", True), ("Emsar", True)], True),
            "NoStargateNamedForTheNextSystem")

    def test_two_gates_named_for_one_system_decline(self):
        """Not something a reading can choose between, so it does not."""
        self.assertEqual(
            self.answers("Adirain", [("Adirain", True), ("Adirain", False)], True),
            "SeveralStargatesNamedForTheNextSystem")

    def test_no_jump_button_declines(self):
        self.assertEqual(
            self.answers("Adirain", [("Adirain", True)], False),
            "ThePanelOffersNoJump")

    def test_an_empty_overview_declines(self):
        self.assertEqual(
            self.answers("Adirain", [], True),
            "NoStargateNamedForTheNextSystem")

    def test_the_rule_reads_nothing_but_its_own_record(self):
        """No reading, no decision context, so a case can execute it."""
        body = collapsed(without_comments(declaration("routeStargateJump")))
        for reached_for in ("context", "readingFromGameClient", "memory",
                            "overviewWindows", "selectedItemWindow"):
            self.assertNotIn(reached_for, body)


class TheGateNameMatchTest(unittest.TestCase):
    """`stargateNameLeadsToSystem`, which decides which row the route means."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def matches(self, system_name, gate_name):
        return self.repl.evaluate(
            ['stargateNameLeadsToSystem "%s" "%s"' % (system_name, gate_name)])[0]

    def test_the_live_rows_match_their_own_systems(self):
        for name, _ in LIVE_STARGATE_ROWS:
            self.assertTrue(self.matches(name, name), name)

    def test_the_live_rows_do_not_match_each_other(self):
        for system, _ in LIVE_STARGATE_ROWS:
            for name, _ in LIVE_STARGATE_ROWS:
                if name != system:
                    self.assertFalse(self.matches(system, name),
                                     "%s matched %s" % (system, name))

    def test_a_parenthesised_row_name_still_matches(self):
        """The preset this client does not use, and might on another machine."""
        self.assertTrue(self.matches("Adirain", "Stargate (Adirain)"))

    def test_a_system_name_is_not_matched_as_a_substring(self):
        """`Ami` is inside `Amir`, and a substring rule would take it."""
        self.assertFalse(self.matches("Ami", "Amir"))
        self.assertFalse(self.matches("Ami", "Stargate (Amir)"))

    def test_a_hyphenated_system_name_matches_itself(self):
        self.assertTrue(self.matches("1DQ1-A", "1DQ1-A"))
        self.assertTrue(self.matches("1DQ1-A", "Stargate (1DQ1-A)"))

    def test_a_hyphenated_system_does_not_match_its_neighbour(self):
        self.assertFalse(self.matches("1DQ1-A", "Stargate (1DQ1-B)"))

    def test_the_case_the_client_writes_is_not_load_bearing(self):
        self.assertTrue(self.matches("Adirain", "STARGATE (ADIRAIN)"))


class TheNextSystemLabelTest(unittest.TestCase):
    """`parseNextSystemInRouteFromLabelText`, over the client's own markup."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parsed(self, label):
        answers = self.repl.strings([
            'parseNextSystemInRouteFromLabelText "%s"'
            ' |> Maybe.withDefault "<nothing>"'
            % label.replace("\\", "\\\\").replace('"', '\\"')])
        return None if answers[0] == "<nothing>" else answers[0]

    def test_the_live_client_s_label_names_the_next_system(self):
        self.assertEqual(self.parsed(NEXT_SYSTEM_LABEL_LIVE), "Arnon")

    def test_the_2019_recording_s_label_names_it_too(self):
        """Single quotes and `<url=` rather than `<a href=`.

        Both styles for `parseCurrentSolarSystemFromUINodeText`'s reason: this
        repo has readings in each and neither is the one that will arrive next.
        """
        self.assertEqual(self.parsed(NEXT_SYSTEM_LABEL_2019), "Piekura")

    def test_the_destination_label_is_not_read_as_the_next_system(self):
        """It names a system too, and it is the far end of the route."""
        self.assertIsNone(self.parsed(DESTINATION_LABEL_2019))

    def test_a_label_with_no_marker_answers_nothing(self):
        self.assertIsNone(self.parsed("Route <fontsize=12>1 Jump"))

    def test_an_empty_name_answers_nothing(self):
        """Rather than a system called "", which every gate would match."""
        self.assertIsNone(
            self.parsed('<a href="showinfo:5//1" alt="Next System in Route">'
                        '</a>'))

    def test_the_marker_is_the_client_s_own_wording(self):
        body = collapsed(declaration("parseNextSystemInRouteFromLabelText"))
        self.assertIn("alt='Next System in Route'", body)
        self.assertIn('alt=\\"Next System in Route\\"', body)


class TheWordingTest(unittest.TestCase):
    """`describeRouteStargateJump`, which is what an operator reads.

    Executed rather than asserted by substring over the branch: a branch's own
    text quotes the names an assertion would look for, which is how a case
    written to catch a press aimed at the wrong button once passed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()
        cls.sentences = dict(zip(
            ("press", "no_system", "no_gate", "several", "showing_else",
             "no_button"),
            cls.repl.strings([
                'describeRouteStargateJump (PressTheJumpButton "Adirain")',
                "describeRouteStargateJump NoNextSystemOnRoute",
                'describeRouteStargateJump (NoStargateNamedForTheNextSystem "Adirain")',
                'describeRouteStargateJump (SeveralStargatesNamedForTheNextSystem "Adirain")',
                'describeRouteStargateJump (ThePanelIsShowingSomethingElse "Adirain")',
                'describeRouteStargateJump (ThePanelOffersNoJump "Adirain")',
            ])))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_answer_reads_differently(self):
        self.assertEqual(len(set(self.sentences.values())),
                         len(self.sentences))

    def test_the_press_names_the_gate_and_says_the_panel_already_showed_it(self):
        sentence = self.sentences["press"]
        self.assertIn("Adirain", sentence)
        self.assertIn("already showing", sentence)

    def test_every_fall_back_names_the_route_marker(self):
        for key, sentence in self.sentences.items():
            if key != "press":
                self.assertIn("route marker", sentence, key)

    def test_no_fall_back_reads_as_a_press(self):
        for key, sentence in self.sentences.items():
            if key != "press":
                self.assertNotIn("Jump through", sentence, key)

    def test_the_ones_that_know_a_system_name_it(self):
        for key in ("no_gate", "several", "showing_else", "no_button"):
            self.assertIn("Adirain", self.sentences[key], key)

    def test_the_showing_something_else_sentence_says_what_selecting_costs(self):
        """The one departure from `selectThenPanelAction`, said out loud."""
        self.assertIn("spend the reading", self.sentences["showing_else"])

    def test_the_system_named_is_the_one_it_was_given(self):
        other = self.repl.strings([
            'describeRouteStargateJump (ThePanelIsShowingSomethingElse "Emsar")'
        ])[0]
        self.assertIn("Emsar", other)
        self.assertNotIn("Adirain", other)


class TheWiringTest(unittest.TestCase):
    """What the branch hands the rule, and where the branch sits.

    Not expressions, so read out of the source -- through the indentation
    reader, since the record `verdict` is bound to is exactly the shape a
    blank-line or next-binding reader stops at.
    """

    def test_the_travel_leg_tries_the_panel_before_the_route_marker(self):
        body = collapsed(without_comments(declaration("jumpToNextSystem")))
        self.assertIn(
            "dockAtDestinationStation context (jumpThroughRouteStargate "
            "context (routeMarkerCascade context infoPanelRouteFirstMarker) )",
            body)

    def test_the_gates_offered_to_the_rule_are_rendered_stargates(self):
        binding = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn("List.filter overviewEntryIsDisplayed", binding)
        self.assertIn("List.filter overviewEntryIsAStargate", binding)

    def test_each_gate_carries_whether_the_panel_is_showing_that_gate(self):
        """Per row, not once for the panel.

        `selectedItemIsOverviewEntry` takes the entry, so a version that asked
        it about something else -- or about the first gate and used the answer
        for all of them -- would jump on a panel showing a different gate.
        """
        binding = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn(
            "List.map (\\gate -> { name = gate.objectName "
            '|> Maybe.withDefault "" , panelIsShowingIt = '
            "selectedItemIsOverviewEntry context gate } )",
            binding)

    def test_the_next_system_comes_from_the_route_panel(self):
        binding = indented_binding("jumpThroughRouteStargate", "verdict")
        self.assertIn(
            "nextSystemOnRoute = nextSystemOnRouteFromReading "
            "context.readingFromGameClient",
            binding)

    def test_the_button_offered_is_the_button_pressed(self):
        """One lookup, so the rule cannot be told about a button the branch
        then declines to press -- or press one it was never told about."""
        body = collapsed(without_comments(declaration("jumpThroughRouteStargate")))
        self.assertIn(
            'jumpButton = selectedItemButtonNamed context "%s"' % JUMP_BUTTON,
            body)
        self.assertIn("panelOffersJump = jumpButton /= Nothing", body)
        self.assertIn("( PressTheJumpButton _, Just buttonToPress ) ->", body)
        self.assertIn("clickUiElement buttonToPress", body)
        self.assertEqual(body.count(JUMP_BUTTON), 1)

    def test_it_never_selects_a_row_first(self):
        """`selectThenPanelAction`'s third branch, deliberately absent.

        Selecting spends the reading this exists to save, and the fall-back
        travels the route regardless -- so there is exactly one click here and
        it is the panel's button.
        """
        body = collapsed(without_comments(declaration("jumpThroughRouteStargate")))
        self.assertEqual(body.count("clickUiElement"), 1)
        self.assertNotIn("entry.uiNode", body)
        self.assertNotIn("gate.uiNode", body)

    def test_the_fall_back_hands_the_caller_s_own_step_back(self):
        """It does not wait, which is what `selectThenPanelAction` does.

        Waiting here would stop the route being travelled at all on every
        reading the gate cannot be identified from -- which is most of them.
        """
        body = collapsed(without_comments(declaration("jumpThroughRouteStargate")))
        self.assertIn(
            "describeBranch (describeRouteStargateJump verdict) "
            "ifThePanelCannotDoIt",
            body)
        self.assertNotIn("waitForProgressInGame", body)
        self.assertNotIn("askForHelpToGetUnstuck", body)

    def test_both_branches_say_which_answer_they_took(self):
        body = collapsed(without_comments(declaration("jumpThroughRouteStargate")))
        self.assertEqual(body.count("describeRouteStargateJump verdict"), 2)

    def test_the_route_marker_cascade_is_otherwise_unchanged(self):
        """Still both entries, still its own widened tolerance.

        The tolerance is why this cascade is worth replacing readings of, and
        the "dock" entry is what flies an out-of-range dock -- neither is
        touched by adding a path in front of it.
        """
        body = collapsed(without_comments(declaration("routeMarkerCascade")))
        self.assertIn("toleratedDistance = 200", body)
        self.assertIn('[ "dock" , "jump" ]', body)

    def test_the_stargate_predicate_has_one_definition(self):
        """Read by the retreat's escape target and by the jump leg.

        `overviewEntryIsAStation`'s own comment argues this for stations, and
        the second reader here decides which object a jump acts on.
        """
        source = bot_elm()
        predicate = collapsed(without_comments(
            declaration("overviewEntryIsAStargate", source)))
        self.assertIn("[ entry.objectName, entry.objectType ]", predicate)
        self.assertIn('containsWords "stargate"', predicate)
        escape = collapsed(without_comments(
            declaration("escapeTargetOnOverview", source)))
        self.assertIn("List.filter overviewEntryIsAStargate", escape)
        self.assertEqual(source.count('containsWords "stargate"'), 1)

    def test_only_the_row_s_name_is_matched_against_the_route_s_system(self):
        """A type reads `Stargate (Amarr Border)` and Amarr is a real system.

        So the identity match looks at the Name column alone, while the
        "is this a stargate" question looks at both.
        """
        body = collapsed(without_comments(declaration("routeStargateJump")))
        self.assertIn(".name >> stargateNameLeadsToSystem nextSystem", body)
        self.assertNotIn("objectType", body)


class TheCorpusTest(unittest.TestCase):
    """What the cascade this replaces actually costs, out of `~/eve-bot-logs`.

    Counted in readings rather than decision lines. The bot re-derives its whole
    decision path on every framework event, so a leg that looks like a dozen
    lines is two or three readings -- and counting the other way is how this
    repo has twice calibrated a threshold against the wrong statistic.
    """

    def episodes_by_run(self):
        found = recorded_runs("35", "37")
        return [(name, cascade_episodes(path)) for name, path in found]

    def test_the_cascade_costs_more_than_one_reading_on_a_jump_leg(self):
        """Otherwise there is nothing here to save."""
        for name, episodes in self.episodes_by_run():
            if not episodes:
                continue
            spent = sum(len(episode) for episode in episodes)
            self.assertGreater(
                spent, len(episodes),
                "run %s: %d readings across %d legs" % (name, spent, len(episodes)))

    def test_the_saving_is_a_reading_or_two_rather_than_a_rescue(self):
        """The doc comment's claim, asserted so it cannot quietly become false.

        A median leg costing many readings would mean the cascade is failing
        rather than merely being clumsy, and the change would be described
        wrongly -- which matters more here than the number does, because the
        risk it is weighed against is a wrong system.
        """
        for name, episodes in self.episodes_by_run():
            if not episodes:
                continue
            self.assertLessEqual(
                median([len(episode) for episode in episodes]), 5,
                "run %s" % name)

    def test_some_legs_cost_far_more_than_the_median(self):
        """The tail the widened tolerance was written for is real."""
        worst = 0
        for _, episodes in self.episodes_by_run():
            for episode in episodes:
                worst = max(worst, len(episode))
        self.assertGreaterEqual(worst, 10)

    def test_the_doc_comment_s_counts_are_what_the_runs_hold(self):
        """The numbers `jumpThroughRouteStargate` quotes, recomputed.

        Read out of the source and checked against the corpus, the way the
        docking run-in's marker is: a doc comment that quotes a measurement
        nobody can reproduce is how a claim survives the evidence for it.
        """
        quoted = doc_comment("jumpThroughRouteStargate")
        expected = {
            "35": (int(re.search(
                r"run 35 \*\*(\d+) readings across (\d+) jump legs",
                quoted).group(1)),
                int(re.search(
                    r"run 35 \*\*(\d+) readings across (\d+) jump legs",
                    quoted).group(2))),
            "37": (int(re.search(
                r"run 37 \*\*(\d+) across (\d+)\*\*", quoted).group(1)),
                int(re.search(
                    r"run 37 \*\*(\d+) across (\d+)\*\*", quoted).group(2))),
        }
        for name, episodes in self.episodes_by_run():
            spent = sum(len(episode) for episode in episodes)
            self.assertEqual((spent, len(episodes)), expected[name],
                             "run %s" % name)

    def test_the_panel_path_would_have_had_something_to_identify(self):
        """Every recorded jump leg is one the route panel was naming a system
        on -- the branch is only reached under `A route is set`, which the
        readings the cascade runs in all carry.
        """
        for name, path in recorded_runs("35", "37"):
            readings = readings_with_decisions(path)
            marked = [index for index, decisions in enumerate(readings)
                      if any(CASCADE_OPEN in line for line in decisions)]
            self.assertTrue(marked, "run %s records no route cascade" % name)
            for index in marked:
                self.assertTrue(
                    any("A route is set" in line
                        for line in readings[index]),
                    "run %s reading %d" % (name, index))


if __name__ == "__main__":
    unittest.main()
