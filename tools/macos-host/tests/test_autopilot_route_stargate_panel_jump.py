"""Tests for the warp-to-0 autopilot jumping the route's next stargate from the
Selected Item panel rather than by right-clicking the route panel's marker.

This is PR #170's rule, ported from saxrat's copy of it (#169). Issue #300.

**What it costs here, measured on this bot's own runs rather than taken from the
issue.** Counted in *readings* -- the framework re-derives its whole decision
path several times per reading, so decision lines are a ratio and not a count --
the route cascade's three rungs hold **401 of the 649 readings** in the six
recorded runs in `~/eve-bot-logs/autopilot_run*.log`, **62%**, across the **21**
jumps those runs completed: about **19 readings a jump**. The mission runner
answers 3 and 2 readings a leg on the same measurement and saxrat 12 and 13, so
this is the most expensive copy of this cascade in the repo, on the bot whose
whole job is travelling. `TheCorpusTest` re-takes all of that from the logs as
relations rather than as the numbers the doc comment quotes, so a corpus that
grows cannot turn a true claim red.

Two things make it worse here than in either of the other apps, and neither is
changed by this PR:

* this bot right-clicks the 8x8 route icon through the **shared 70px** tolerance.
  The mission runner widened its own copy of this same cascade to **200** because
  `"Jump Through Stargate"` "took 3-4 menu opens before being recognized", and
  this bot never got that widening. `TheCascadeIsUnchangedTest` pins that it is
  still the shared `useContextMenuCascade`, so a later change to it is a
  deliberate one.
* run 6's log carries `All of route element icon ... is occluded by 3 context
  menu region(s)` -- the menu the previous attempt opened is what hides the
  target of the next one.

**The identity condition is the whole safety of this change**, and most of the
cases below are about it. A jump to the wrong gate is a wrong *system*, not a
wasted tick. `InfoPanelRouteRouteElementMarker` carries a `uiNode` and no name,
so the marker cannot say which gate it is; what answers is two other things the
client renders:

    route panel:  <a href="showinfo:5//30005001" alt="Next System in Route">Arnon</a>
    overview row: Name "Tar"   Type "Stargate (CONCORD System)"
    panel label:  Tar (<color=#ff4ecef8>0.8</color>)

`TheWrongSystemIsRefusedTest` is the case this whole design exists for, and it is
run through the real parser end to end: a reading whose only stargate row names a
system the route did not, and a reading whose row *type* names the route's system
while its Name names another. The second is the one that catches a rule reading
both columns -- a type reads `Stargate (Amarr Border)` and Amarr is a real
system.

**When the panel declines, the bot right-clicks the route marker, exactly as it
does today.** `TheFallBackIsTheCascadeTest` asserts that in both directions: the
fall-back handed in is `routeMarkerCascade`, and the branch reaches for nothing
that could stall instead -- no wait, no session finish, no ask-for-help.

**The dock leg deliberately did not move**, and `TheDockLegDidNotMoveTest` pins
it rather than leaving it to be rediscovered. `useMenuEntryWithTextContainingFirstOf`
takes **dock before jump**, which is how this bot ends its own session at the
final waypoint -- observed live on 2026-08-16. #99's docking run-in says a
cascade cannot finish a dock on the *mission runner*, but that bot has a run-in
guard and a `dockAtDestinationStation` panel branch and this one has neither, so
that evidence does not carry across. Changing the dock leg needs its own.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, and the readings they are asked about go through the real
`EveOnline.ParseUserInterface`. The fixture builders and the source readers are
imported from the saxrat files that already have them rather than copied: eleven
copies is how eleven probes drifted.

Nothing here reads a live game client or drives a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import (ElmRepl, EVE_BOT_LOGS, REPO_DIR, open_repl,
                           recorded_runs)
from test_saxrat_ported_guards import (
    SaxratRepl, body_of, collapsed, overview, source_of)
from test_saxrat_route_stargate_panel_jump import (
    DESTINATION_LABEL_2019, JUMP_BUTTON, NEXT_SYSTEM_LABEL_2019,
    NEXT_SYSTEM_LABEL_LIVE, readings_with_decisions, route_panel,
    selected_item_window, without_comments)

AUTOPILOT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-warp-to-0-autopilot")
AUTOPILOT_BOT_ELM = os.path.join(AUTOPILOT_DIR, "Bot.elm")
SAXRAT_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat",
    "Bot.elm")
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Stargate rows as the client renders them. The destination system alone in the
# Name column, the word in the Type column, and the region riding along in the
# type -- which is the column the identity match must never read.
LIVE_STARGATE_ROWS = [
    ("Tar", "Stargate (CONCORD System)"),
    ("Emsar", "Stargate (CONCORD System)"),
    ("Tolle", "Stargate (Gallente Border)"),
]

# What the Selected Item panel's `nameLabel` reads with the `Tar` gate selected.
LIVE_PANEL_NAME_LABEL = "Tar (<color=#ff4ecef8>0.8</color>)"

# The row that catches a rule reading the Type column: its type names Amarr, and
# Amarr is a real system, but the gate leads to Emsar.
AMARR_BORDER_ROW = ("Emsar", "Stargate (Amarr Border)")

# This bot's cascade rungs. The click line differs from the mission runner's and
# saxrat's because this bot's entry list also carries the Korean spellings, so
# the prefix is all that can be shared.
CASCADE_OPEN = "Open context menu on route element icon"
CASCADE_CLICK = "first available of 'dock'"
CASCADE_WAIT = "No context menu in this reading yet"

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# `reading_binding` builds a JSON literal and pipes it through the parser named
# in the string; nothing in it is saxrat's, so it is called as the static
# function it is rather than copied for a third app.
reading_binding = SaxratRepl.reading_binding


def shared_rung_readings(readings):
    """Readings holding a rung both bots' route cascades print identically.

    The open and the wait, not the click: this bot's entry list carries the
    Korean spellings too, so its click line reads differently and counting it on
    one side only would flatter whichever side had it.
    """
    return sum(
        1 for decisions in readings
        if any(rung in line
               for line in decisions
               for rung in (CASCADE_OPEN, CASCADE_WAIT)))


def hide_overview_row(overview_window, index):
    """Turn one overview row's own `_display` flag off, in place.

    A row scrolled out of the overview keeps a plausible region pointing at a
    row that now belongs to something else, so an undisplayed row can name a
    system the bot would then believe a gate for. `overview` builds every row
    displayed, and this is the only way to build the other kind.
    """
    rows = overview_window["children"][0]["children"][1:]
    rows[index]["dictEntriesOfInterest"]["_display"] = False
    return overview_window


def autopilot_source():
    return source_of(AUTOPILOT_BOT_ELM)


def doc_comment(name, path=AUTOPILOT_BOT_ELM):
    """The `{-| … -}` block immediately above a declaration's annotation.

    Read separately because `body_of` starts at the type annotation, and the
    measurement `TheCorpusTest` re-takes is quoted in the prose.
    """
    source = source_of(path)
    annotation = source.index("\n%s :" % name)
    opened = source.rindex("{-|", 0, annotation)
    closed = source.index("-}", opened)
    return collapsed(source[opened:closed])


def indented_binding(declaration_name, name, path=AUTOPILOT_BOT_ELM):
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


def autopilot_runs():
    """The recorded warp-to-0 runs this machine has, or the shared skip.

    The autopilot's logs are named `autopilot_run*.log` and are not reachable
    through `prerequisites.recorded_runs`, which knows only the mission runner's
    naming. The wording is the one `check_expected_skips.py` already accepts for
    a missing corpus.
    """
    logs = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "autopilot_run*.log")))
    if not logs:
        raise unittest.SkipTest(
            "no recorded runs of the warp-to-0 autopilot in ~/eve-bot-logs, so "
            "what those runs say this cascade costs cannot be consulted here")
    return logs


class AutopilotRepl(ElmRepl):
    """The same harness, pointed at the warp-to-0 autopilot."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "autopilot-repl-")
        kwargs.setdefault("app_dir", AUTOPILOT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class ReplCase(unittest.TestCase):
    """One repl per class, opened through the probe."""

    repl = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(AutopilotRepl)

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()


class TheRuleTest(ReplCase):
    """`routeStargateJump`, executed at each of its six answers.

    Every case asks all six equalities rather than the one it expects, so a rule
    that answers two things at once -- or none -- fails rather than passing on
    whichever constructor the case happened to name.
    """

    def answers(self, next_system, gates, offers_jump):
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
        pressed = '"%s"' % (gates[0][0] if gates else "no gate at all")
        return self.repl.evaluate([
            "(%s) == PressTheJumpButton %s" % (given, pressed),
            "(%s) == NoNextSystemOnRoute" % given,
            '(%s) == NoStargateNamedForTheNextSystem "%s"' % (given, next_system),
            '(%s) == SeveralStargatesNamedForTheNextSystem "%s"' % (given, next_system),
            '(%s) == ThePanelIsShowingSomethingElse "%s"' % (given, next_system),
            '(%s) == ThePanelOffersNoJump "%s"' % (given, next_system),
        ])

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
        """The first refusal. The button is offered and the route's gate is on
        the overview -- but the panel is showing something else, so pressing Jump
        acts on whatever that is. It falls back rather than selecting the row
        first, because selecting spends the reading this exists to save.
        """
        self.expect("panel showing something else", "Tar",
                    [("Tar", False)], True)

    def test_no_named_next_system_declines(self):
        """The second refusal. Nothing says which stargate the route means."""
        self.expect("no next system", None, [("Tar", True)], True)

    def test_no_gate_named_for_the_next_system_declines(self):
        """The third refusal, and the wrong-system hazard in its plainest form:
        the overview's only gate leads somewhere the route did not name."""
        self.expect("no gate named", "Tar", [("Tolle", True)], True)

    def test_two_gates_named_for_one_system_decline(self):
        """The fourth refusal. A system's name is unique, so two rows naming it
        is not a choice this reading can make."""
        self.expect("several gates", "Tar",
                    [("Tar", True), ("Tar", False)], True)

    def test_no_jump_button_declines(self):
        """The fifth refusal. The gate is out of jump range, and it is the
        cascade that closes the distance."""
        self.expect("no jump button", "Tar", [("Tar", True)], False)

    def test_an_empty_overview_declines(self):
        """Run 42's shape: no gate on the overview at all, so the panel jump
        correctly declines and the cascade is the only way out."""
        self.expect("no gate named", "Tar", [], True)

    def test_the_rule_reads_nothing_but_its_own_record(self):
        """It takes three named fields and reaches for no reading and no context,
        which is what lets every case above execute it."""
        body = collapsed(without_comments(
            body_of(autopilot_source(), "routeStargateJump")))
        for forbidden in ("readingFromGameClient", "BotDecisionContext",
                          "context.memory", "overviewWindows"):
            self.assertNotIn(forbidden, body)


class TheWrongSystemIsRefusedTest(ReplCase):
    """The failure this change could introduce, refused through the real parser.

    Not the rule asked in isolation -- a whole reading, decoded and parsed, with
    the overview rows and the panel the client would have drawn. What is asserted
    is the verdict the wiring in `jumpThroughRouteStargate` would have computed
    from it, so a wiring that hands the rule the wrong column fails here even
    though the rule itself is correct.
    """

    def verdict(self, next_system_label, rows, panel_showing,
                buttons=(JUMP_BUTTON,), hide_rows=()):
        """The bot's own verdict for a parsed reading, rendered.

        `routeStargateJumpFromReading` is **the shipped wiring**, not a copy of
        it written here: which column reaches the identity match, which rows are
        offered, and whether the panel is asked for the button are all decided
        inside it. A case that rebuilt that record in Python would pass on a
        wiring that reads the Type column, which is the whole hazard.
        """
        overview_window = overview([("8,998 m", name, object_type)
                                    for name, object_type in rows])
        for index in hide_rows:
            hide_overview_row(overview_window, index)
        children = [route_panel([next_system_label]), overview_window]
        if panel_showing is not None:
            children.append(selected_item_window(panel_showing, buttons))
        definition = reading_binding("reading", children)
        return self.repl.strings([
            'reading |> Maybe.map (routeStargateJumpFromReading'
            ' >> describeRouteStargateJump)'
            ' |> Maybe.withDefault "no reading at all"'
        ], definitions=[definition])[0]

    def test_the_route_s_own_gate_is_jumped(self):
        """The control. Everything below differs from this in one reading."""
        answer = self.verdict(
            '<center><a href="showinfo:5//1" alt="Next System in Route">Tar</a>',
            LIVE_STARGATE_ROWS, LIVE_PANEL_NAME_LABEL)
        self.assertIn("Jump through 'Tar'", answer)

    def test_a_row_whose_name_is_not_the_route_s_system_is_not_jumped(self):
        """**The wrong-system hazard.** The panel is showing a gate and offering
        Jump, and the gate leads to Emsar while the route says Arnon. Pressing it
        would put the ship in the wrong system, which is not a wasted tick.
        """
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,  # names Arnon
            [("Emsar", "Stargate (CONCORD System)")],
            "Emsar (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("No stargate on the overview is named for 'Arnon'",
                      answer)
        self.assertNotIn("Jump through", answer)

    def test_a_row_whose_type_names_the_route_s_system_is_not_jumped(self):
        """The same hazard wearing the shape a careless rule would fall for.

        The route says Amarr. The overview's one gate has `Amarr` in its **Type**
        -- `Stargate (Amarr Border)` -- and leads to Emsar. A rule that matched
        either column would jump it, and Amarr is a real system, so the log line
        would read like a success.
        """
        answer = self.verdict(
            '<center><a href="showinfo:5//2" alt="Next System in Route">'
            'Amarr</a>',
            [AMARR_BORDER_ROW],
            "Emsar (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("No stargate on the overview is named for 'Amarr'",
                      answer)
        self.assertNotIn("Jump through", answer)

    def test_the_type_text_would_have_matched_on_its_own(self):
        """Which is what makes the case above a real hazard rather than a
        hypothetical one: the words do match, and only the choice of column
        keeps them apart."""
        self.assertEqual(
            self.repl.evaluate([
                'stargateNameLeadsToSystem "Amarr" "%s"' % AMARR_BORDER_ROW[1],
                'stargateNameLeadsToSystem "Amarr" "%s"' % AMARR_BORDER_ROW[0],
            ]),
            [True, False])

    def test_only_the_name_column_reaches_the_identity_match(self):
        wiring = collapsed(without_comments(
            body_of(autopilot_source(), "routeStargateJumpFromReading")))
        self.assertIn("name = gate.objectName", wiring)
        self.assertNotIn("objectType", wiring)

    def test_two_gates_to_one_system_on_a_real_reading_decline(self):
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,
            [("Arnon", "Stargate (Amarr System)"),
             ("Arnon", "Stargate (Amarr Border)")],
            "Arnon (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("More than one stargate", answer)
        self.assertNotIn("Jump through", answer)

    def test_a_panel_showing_another_gate_on_a_real_reading_declines(self):
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,
            [("Arnon", "Stargate (Amarr System)"),
             ("Tolle", "Stargate (Gallente Border)")],
            "Tolle (<color=#ff4ecef8>0.5</color>)")
        self.assertIn("not showing the stargate to 'Arnon'", answer)
        self.assertNotIn("Jump through", answer)

    def test_a_panel_without_the_button_on_a_real_reading_declines(self):
        """An out-of-range gate: the panel is showing it and draws no Jump."""
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,
            [("Arnon", "Stargate (Amarr System)")],
            "Arnon (<color=#ff4ecef8>0.8</color>)",
            buttons=("selectedItemOrbit",))
        self.assertIn("offers no 'selectedItemJump'", answer)
        self.assertNotIn("Jump through", answer)

    def test_no_selected_item_window_at_all_declines(self):
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,
            [("Arnon", "Stargate (Amarr System)")],
            None)
        self.assertIn("not showing the stargate to 'Arnon'", answer)
        self.assertNotIn("Jump through", answer)

    def test_a_route_panel_that_names_no_next_system_declines(self):
        answer = self.verdict(
            "Route <fontsize=12></b>3 Jumps",
            [("Arnon", "Stargate (Amarr System)")],
            "Arnon (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("does not name a next system", answer)
        self.assertNotIn("Jump through", answer)

    def test_a_row_the_client_is_not_drawing_is_not_believed(self):
        """A row scrolled out of the overview keeps a plausible region pointing
        at a row that now belongs to something else. Here the route's own gate
        is the undisplayed one, so believing it would jump on a row the client
        is not showing; the reading falls back instead.
        """
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,  # names Arnon
            [("Arnon", "Stargate (Amarr System)"),
             ("Tolle", "Stargate (Gallente Border)")],
            "Arnon (<color=#ff4ecef8>0.8</color>)",
            hide_rows=(0,))
        self.assertIn("No stargate on the overview is named for 'Arnon'",
                      answer)
        self.assertNotIn("Jump through", answer)

    def test_the_same_row_displayed_is_believed(self):
        """The control for the case above, differing in the one flag."""
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,
            [("Arnon", "Stargate (Amarr System)"),
             ("Tolle", "Stargate (Gallente Border)")],
            "Arnon (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("Jump through 'Arnon'", answer)

    def test_an_overview_with_no_stargate_declines(self):
        """Run 42's shape, on a real reading."""
        answer = self.verdict(
            NEXT_SYSTEM_LABEL_LIVE,
            [("Beacon", "Beacon"), ("Naglfar Wreck", "Naglfar Wreck")],
            "Beacon")
        self.assertIn("No stargate on the overview is named for 'Arnon'",
                      answer)
        self.assertNotIn("Jump through", answer)


class TheNextSystemLabelTest(ReplCase):
    """`nextSystemOnRouteFromReading`, over the client's own markup.

    This bot had never read the route panel's text at all -- only whether it
    held a marker -- so every one of these is a first reading here.
    """

    def parsed(self, labels):
        definition = reading_binding("reading", [route_panel(labels)])
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
        """The panel names two systems and only one of them is the next hop.
        Reading the other would jump towards the far end of the route."""
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
        definition = reading_binding("reading", [overview([])])
        self.assertEqual(
            self.repl.strings(
                ['reading |> Maybe.andThen nextSystemOnRouteFromReading'
                 ' |> Maybe.withDefault "nothing"'],
                definitions=[definition])[0],
            "nothing")

    def test_the_marker_is_the_client_s_own_wording(self):
        body = collapsed(body_of(autopilot_source(),
                                 "parseNextSystemInRouteFromLabelText"))
        self.assertIn("alt='Next System in Route'", body)
        self.assertIn('alt=\\"Next System in Route\\"', body)


class ThePanelReadersTest(ReplCase):
    """The two readers this bot did not have, on parsed readings.

    `selectedItemButtonNamed` is the helper #300 names as the thing to port, and
    `ParseUserInterface` exposes only `orbitButton` off this window in this bot's
    parser as in saxrat's -- so this is what makes a panel press possible without
    a parser change.
    """

    def button_present(self, buttons, wanted=JUMP_BUTTON):
        definition = reading_binding(
            "reading", [selected_item_window("Tar", buttons)])
        return self.repl.evaluate([
            'reading |> Maybe.map (\\r -> selectedItemButtonNamed r "%s"'
            ' /= Nothing) |> Maybe.withDefault False' % wanted
        ], definitions=[definition])[0]

    def test_the_jump_button_is_found_by_its_own_name(self):
        self.assertTrue(self.button_present([JUMP_BUTTON]))

    def test_a_panel_drawing_other_buttons_offers_no_jump(self):
        """An out-of-range gate, and the acceleration gate's own button, neither
        of which is a jump."""
        self.assertFalse(
            self.button_present(["selectedItemOrbit",
                                 "selectedItemActivateGate"]))

    def test_a_reading_with_no_panel_offers_no_jump(self):
        definition = reading_binding("reading", [overview([])])
        self.assertEqual(
            self.repl.evaluate([
                'reading |> Maybe.map (\\r -> selectedItemButtonNamed r "%s"'
                ' /= Nothing) |> Maybe.withDefault False' % JUMP_BUTTON
            ], definitions=[definition]),
            [False])

    def showing(self, panel_text, row_names):
        rows = [("8,998 m", name, "Stargate (CONCORD System)")
                for name in row_names]
        definition = reading_binding("reading", [
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
        definition = reading_binding("reading", [
            overview([("8,998 m", name, object_type)
                      for name, object_type in LIVE_STARGATE_ROWS])])
        self.assertEqual(
            self.repl.evaluate([
                'reading |> Maybe.map (\\r -> r.overviewWindows'
                ' |> List.concatMap .entries'
                ' |> List.all overviewEntryIsAStargate)'
                ' |> Maybe.withDefault False'],
                definitions=[definition]),
            [True])

    def test_a_row_that_is_not_a_stargate_is_declined(self):
        definition = reading_binding("reading", [
            overview([("2 m", "Beacon", "Beacon"),
                      ("1,600 m", "Naglfar Wreck", "Naglfar Wreck")])])
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
            body_of(autopilot_source(), "overviewEntryIsAStargate")))
        self.assertIn("entry.objectName", body)
        self.assertIn("entry.objectType", body)


class TheGateNameMatchTest(ReplCase):
    """`stargateNameLeadsToSystem`, over the rows the client really draws."""

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

    def test_a_parenthesised_row_name_still_matches(self):
        """An overview preset can render `Stargate (Tar)` in the Name column."""
        self.assertEqual(
            self.matches([("Tar", "Stargate (Tar)"), ("Tar", "Tar - Stargate"),
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


class TheWordingTest(ReplCase):
    """`describeRouteStargateJump`, rendered rather than asserted by substring.

    A case that asserts a name appears somewhere in the branch can pass on the
    branch's own log text quoting it.
    """

    rendered = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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

    def test_every_answer_reads_differently(self):
        self.assertEqual(len(set(self.rendered.values())),
                         len(self.rendered))

    def test_the_press_names_the_gate_and_says_the_panel_already_showed_it(self):
        press = self.rendered["press"]
        self.assertIn("'Tar'", press)
        self.assertIn("already showing it", press)

    def test_every_fall_back_names_the_route_marker(self):
        """This is how an operator reading a stretch of these sees the cascade is
        still travelling the route rather than that the jump has stopped
        happening."""
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

    def test_the_system_named_is_the_one_it_was_given(self):
        other = self.repl.strings([
            'describeRouteStargateJump (NoStargateNamedForTheNextSystem "Emsar")'
        ])[0]
        self.assertIn("'Emsar'", other)
        self.assertNotIn("Tar", other)


class TheFallBackIsTheCascadeTest(unittest.TestCase):
    """**What the bot does when the panel jump declines**, asserted in both
    directions.

    It right-clicks the route panel's first marker and takes `dock` or `jump`
    from the context menu -- which is exactly what it did on every reading before
    this change, so a decline costs nothing and strands nothing. The risk worth
    pinning is the other one: a fall-back that waits, finishes the session, or
    asks for help would turn every unreadable reading into a stall, and this bot
    has no other way to travel.
    """

    def setUp(self):
        self.source = autopilot_source()
        self.in_space = collapsed(without_comments(
            body_of(self.source, "decideStepWhenInSpace")))
        self.branch = collapsed(without_comments(
            body_of(self.source, "jumpThroughRouteStargate")))

    def test_the_cascade_is_what_is_handed_in_as_the_fall_back(self):
        self.assertIn(
            "jumpThroughRouteStargate context (routeMarkerCascade context"
            " infoPanelRouteFirstMarker)", self.in_space)

    def test_the_panel_is_tried_before_the_cascade(self):
        self.assertLess(self.in_space.index("jumpThroughRouteStargate"),
                        self.in_space.index("routeMarkerCascade"))

    def test_the_fall_back_hands_the_caller_s_own_step_back(self):
        """Not a step of its own. Whatever the caller passed is what runs."""
        self.assertIn("ifThePanelCannotDoIt", self.branch)

    def test_the_decline_cannot_stall(self):
        """The failure mode this bot could not survive: it has no second way to
        travel a route."""
        for forbidden in ("waitForProgressInGame", "FinishSession",
                          "askForHelpToGetUnstuck", "endDecisionPath"):
            self.assertNotIn(forbidden, self.branch, forbidden)

    def test_it_never_selects_a_row_first(self):
        """The one departure from a select-then-press shape: selecting spends the
        reading this exists to save, and the cascade is the fall-back anyway."""
        for forbidden in ("clickUiElement gate", "SelectTheGate",
                          "clickUiElement row"):
            self.assertNotIn(forbidden, self.branch)

    def test_both_branches_say_which_answer_they_took(self):
        self.assertEqual(
            self.branch.count("describeBranch (describeRouteStargateJump verdict)"),
            2)

    def test_the_button_offered_is_the_button_pressed(self):
        """The lookup and the press are the same value, so a press cannot land on
        a button the rule was not told about."""
        lookup = indented_binding("jumpThroughRouteStargate", "jumpButton")
        self.assertIn(
            "routeStargateJumpButton context.readingFromGameClient", lookup)
        self.assertIn(
            'selectedItemButtonNamed readingFromGameClient "%s"' % JUMP_BUTTON,
            collapsed(without_comments(
                body_of(autopilot_source(), "routeStargateJumpButton"))))
        self.assertIn(
            "( PressTheJumpButton _, Just buttonToPress ) -> describeBranch"
            " (describeRouteStargateJump verdict)"
            " (clickUiElement buttonToPress)", self.branch)

    def test_the_branch_uses_the_shipped_wiring_rather_than_one_of_its_own(self):
        """One place decides the verdict, and it is the one the cases above
        execute against parsed readings."""
        self.assertIn(
            "verdict = routeStargateJumpFromReading"
            " context.readingFromGameClient", self.branch)
        self.assertNotIn("routeStargateJump {", self.branch)

    def test_the_rule_is_told_whether_the_button_is_really_there(self):
        """`panelOffersJump` is the lookup, not a constant.

        `test_no_jump_button_declines` asks the rule directly, so it cannot see
        this: a wiring that always says the button is there leaves the rule
        answering `PressTheJumpButton` while the tuple match still falls back,
        and the decision log then claims a press on every reading the panel
        offers nothing.
        """
        wiring = collapsed(without_comments(
            body_of(autopilot_source(), "routeStargateJumpFromReading")))
        self.assertIn(
            "panelOffersJump = routeStargateJumpButton readingFromGameClient"
            " /= Nothing", wiring)

    def test_the_gates_offered_to_the_rule_are_rendered_stargates(self):
        wiring = collapsed(without_comments(
            body_of(autopilot_source(), "routeStargateJumpFromReading")))
        self.assertIn("overviewEntryIsDisplayed", wiring)
        self.assertIn("overviewEntryIsAStargate", wiring)

    def test_each_gate_carries_whether_the_panel_is_showing_that_gate(self):
        """Per row, not once for the whole overview -- a single answer computed
        outside the map would report the same thing about every gate."""
        wiring = collapsed(without_comments(
            body_of(autopilot_source(), "routeStargateJumpFromReading")))
        self.assertIn(
            "panelIsShowingIt = selectedItemIsOverviewEntry"
            " readingFromGameClient gate", wiring)

    def test_the_next_system_comes_from_the_route_panel(self):
        wiring = collapsed(without_comments(
            body_of(autopilot_source(), "routeStargateJumpFromReading")))
        self.assertIn(
            "nextSystemOnRoute = nextSystemOnRouteFromReading"
            " readingFromGameClient", wiring)


class TheCascadeIsUnchangedTest(unittest.TestCase):
    """The fall-back itself, which this PR moved but did not alter."""

    def setUp(self):
        self.cascade = collapsed(without_comments(
            body_of(autopilot_source(), "routeMarkerCascade")))

    def test_it_still_right_clicks_the_route_element_icon(self):
        self.assertIn('( "route element icon", infoPanelRouteFirstMarker'
                      ".uiNode )", self.cascade)

    def test_it_still_carries_both_korean_spellings(self):
        """They came from a forum thread and nothing about this change touches
        the language the client is set to."""
        self.assertIn('"도킹"', self.cascade)
        self.assertIn('"점프 - 스타게이트 사용"', self.cascade)

    def test_it_is_still_the_shared_tolerance_rather_than_the_widened_one(self):
        """Stated rather than fixed. The mission runner widened its copy of this
        same cascade to 200 for this same 8x8 icon, and this bot never got that;
        changing it is a separate question with separate evidence, so this pins
        which of the two shapes is in the file.
        """
        self.assertIn("useContextMenuCascade (", self.cascade)
        self.assertNotIn("useContextMenuCascadeWithCustomConfig", self.cascade)
        self.assertNotIn("toleratedDistance", self.cascade)

    def test_there_is_exactly_one_route_cascade_in_the_file(self):
        """One call site. The name also appears in the import list, which is
        why this counts the application rather than the word."""
        source = collapsed(without_comments(autopilot_source()))
        self.assertEqual(source.count("useContextMenuCascade ("), 1)


class TheDockLegDidNotMoveTest(unittest.TestCase):
    """Issue #300 rules the dock leg out of scope, and this is what that means.

    `useMenuEntryWithTextContainingFirstOf` takes the **first** entry it finds,
    and `dock` is ahead of `jump` in the list. At the final waypoint the client
    offers Dock on the route marker, the bot takes it, and the session ends --
    observed live on 2026-08-16, and run 6's log ends with `We finished
    traveling the route.` Only the jump leg moved to the panel.
    """

    def setUp(self):
        self.source = autopilot_source()
        self.cascade = collapsed(without_comments(
            body_of(self.source, "routeMarkerCascade")))

    def test_dock_still_comes_before_jump_in_the_menu_entry_list(self):
        entries = self.cascade[self.cascade.index("useMenuEntryWithText"):]
        self.assertLess(entries.index('"dock"'), entries.index('"jump"'))

    def test_the_bot_presses_no_dock_button_on_the_panel(self):
        """The mission runner's `dockAtDestinationStation` is not ported, and a
        panel dock here would have neither #98's just-undocked guard nor #99's
        run-in guard behind it."""
        source = without_comments(self.source)
        self.assertNotIn("selectedItemDock", source)
        self.assertNotIn("dockAtDestinationStation", source)

    def test_the_only_panel_button_this_bot_presses_is_the_jump(self):
        """One press, added by this change, and nothing else has started
        reaching for a panel button."""
        source = without_comments(self.source)
        self.assertEqual(source.count("selectedItemButtonNamed"), 3,
                         "an annotation, a definition and one call site")
        self.assertEqual(len(re.findall(r'"selectedItem[A-Za-z]+"', source)), 1)
        self.assertIn('"%s"' % JUMP_BUTTON, source)


class ThePortIsFaithfulTest(unittest.TestCase):
    """What was ported, from where, and that it did not drift on the way.

    The rule and its readers are compared against **saxrat's** copy, which is
    where this came from: at the time of the port `routeStargateJump`,
    `describeRouteStargateJump`, `stargateNameLeadsToSystem`,
    `nextSystemOnRouteFromReading`, `parseNextSystemInRouteFromLabelText` and
    `overviewEntryIsAStargate` were byte for byte identical in saxrat and the
    mission runner, so the two had not diverged and either would have done. What
    decided it is the *shape* of the two readers: saxrat's take a
    `ReadingFromGameClient` where the mission runner's take a
    `BotDecisionContext`, and the smaller argument is the one to copy into a bot
    that has no other caller for them.
    """

    SHARED = ["routeStargateJump", "describeRouteStargateJump",
              "stargateNameLeadsToSystem", "punctuationAsSeparators",
              "nextSystemOnRouteFromReading",
              "parseNextSystemInRouteFromLabelText",
              "overviewEntryIsAStargate", "containsWords"]

    def body(self, path, name):
        return collapsed(without_comments(body_of(source_of(path), name)))

    def test_the_rule_matches_saxrat_s_expression_for_expression(self):
        for name in self.SHARED:
            self.assertEqual(self.body(AUTOPILOT_BOT_ELM, name),
                             self.body(SAXRAT_BOT_ELM, name), name)

    def test_the_two_apps_it_was_ported_from_still_agree_with_each_other(self):
        """The divergence check #300 asks for, re-taken on every run rather than
        stated once in a PR body. If these ever differ, the next port has to
        choose rather than assume."""
        for name in self.SHARED:
            self.assertEqual(self.body(SAXRAT_BOT_ELM, name),
                             self.body(MISSION_RUNNER_BOT_ELM, name), name)

    def test_the_readers_took_saxrat_s_shape_rather_than_the_mission_runner_s(self):
        for name in ("selectedItemButtonNamed", "selectedItemIsOverviewEntry"):
            self.assertEqual(self.body(AUTOPILOT_BOT_ELM, name),
                             self.body(SAXRAT_BOT_ELM, name), name)
            self.assertNotEqual(self.body(AUTOPILOT_BOT_ELM, name),
                                self.body(MISSION_RUNNER_BOT_ELM, name), name)

    def test_no_parser_change_was_needed(self):
        """#300's claim, checked: this bot's `SelectedItemWindow` still exposes
        only the two fields it always did, and the jump button is reached by the
        client's own `_name` instead."""
        parser = source_of(os.path.join(
            AUTOPILOT_DIR, "EveOnline", "ParseUserInterface.elm"))
        window = re.search(
            r"type alias SelectedItemWindow =(.*?)\n\n", parser, re.DOTALL)
        self.assertIsNotNone(window)
        self.assertEqual(
            sorted(re.findall(r"[,{]\s*(\w+) :", window.group(1))),
            ["orbitButton", "uiNode"])


class TheCorpusTest(unittest.TestCase):
    """What this bot's own runs say the cascade costs.

    Counted in readings rather than decision lines. The bot re-derives its whole
    decision path on every framework event, so a leg that prints twenty decision
    lines is a handful of readings -- and counting the other way is how this repo
    has twice mis-calibrated a threshold.

    Per *completed jump* rather than per grouped episode, which is the one place
    this departs from the saxrat and mission-runner corpus tests. Episode
    grouping merges two legs of this bot's runs into one: the cascade's wait rung
    prints on so many consecutive readings that the gap between two legs closes.
    `jumps completed` is the bot's own counter and needs no grouping at all.
    """

    def measured(self):
        found = []
        for path in autopilot_runs():
            readings = readings_with_decisions(path)
            if not readings:
                continue
            spent = sum(
                1 for decisions in readings
                if any(rung in line
                       for line in decisions
                       for rung in (CASCADE_OPEN, CASCADE_CLICK, CASCADE_WAIT)))
            with open(path, encoding="utf-8", errors="replace") as handle:
                jumps = [int(value) for value in
                         re.findall(r"jumps completed: (\d+)", handle.read())]
            found.append((os.path.basename(path), len(readings), spent,
                          max(jumps) if jumps else 0))
        return [entry for entry in found if entry[2]]

    def test_the_runs_are_there_to_say_anything_at_all(self):
        self.assertTrue(self.measured(),
                        "no route cascade in any recorded autopilot run")

    def test_the_cascade_holds_most_of_every_reading_in_the_run(self):
        """The share is what makes this worth doing on this bot: it is not a
        per-leg saving of one or two readings, it is the majority of the run."""
        for name, readings, spent, _ in self.measured():
            self.assertGreater(spent, readings // 3,
                               "%s: %d of %d readings" % (name, spent, readings))

    def test_a_completed_jump_costs_many_readings_of_cascade(self):
        for name, _, spent, jumps in self.measured():
            if not jumps:
                continue
            self.assertGreater(spent, 4 * jumps,
                               "%s: %d readings for %d jumps" % (name, spent, jumps))

    def test_it_is_more_expensive_here_than_on_the_mission_runner(self):
        """The comparison the doc comment rests on, executed rather than quoted.

        Both bots measured the same way, in the same unit, off the two rungs
        whose wording they share -- the *click* rung differs, because this bot's
        entry list also carries the Korean spellings, so it is left out of both
        sides rather than counted on one.
        """
        mission = []
        for _, path in recorded_runs("35", "37"):
            readings = readings_with_decisions(path)
            spent = shared_rung_readings(readings)
            if spent:
                mission.append(spent / len(readings))
        self.assertTrue(mission, "no route cascade in the mission runner's runs")

        here = []
        for path in autopilot_runs():
            readings = readings_with_decisions(path)
            if readings:
                here.append(shared_rung_readings(readings) / len(readings))

        self.assertGreater(
            min(here), 3 * max(mission),
            "autopilot shares %s against the mission runner's %s"
            % ([round(share, 3) for share in here],
               [round(share, 3) for share in mission]))

    def test_the_doc_comment_s_counts_are_what_the_runs_hold(self):
        """A claim the corpus stops supporting goes red rather than standing."""
        comment = doc_comment("jumpThroughRouteStargate")
        quoted = re.search(r"\*\*(\d[\d,]*) of (\d[\d,]*)\s+readings\*\*",
                           comment)
        self.assertIsNotNone(
            comment and quoted, "the doc comment quotes no counts: %s" % comment)
        spent_quoted = int(quoted.group(1).replace(",", ""))
        readings_quoted = int(quoted.group(2).replace(",", ""))

        measured = self.measured()
        self.assertEqual(
            (sum(spent for _, _, spent, _ in measured),
             sum(readings for _, readings, _, _ in measured)),
            (spent_quoted, readings_quoted))

    def test_every_recorded_leg_had_a_route_panel_to_read(self):
        """The panel path's first input. A run whose route panel was never there
        is a run this change could not have helped."""
        for path in autopilot_runs():
            readings = readings_with_decisions(path)
            with_route = [
                decisions for decisions in readings
                if not any("I see no route in the info panel" in line
                           for line in decisions)]
            self.assertGreater(len(with_route), len(readings) // 2,
                               os.path.basename(path))


if __name__ == "__main__":
    unittest.main()
