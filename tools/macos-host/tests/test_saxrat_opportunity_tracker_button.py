"""Tests for saxrat taking the Opportunities tracker's own travel button.

`warpToOpportunitySiteIfAvailable` was `findUiElementWithText "Warp to Site"`
over the whole UI tree. The tracker actually renders **one**
`TravelToLocationButtonTaskWidget` whose label changes with what the trip needs
-- read off the live client with five `Sansha's Command Relay Outpost`
escalations in the panel, it says `Jump` while the destination is several jumps
out, `Warping` once the ship is under way, `Warp to Site` in system, and
`Set Destination` before a route exists. So the bot matched one value of four
and ignored the tracker: runs 25 and 26 made 44 and 168 route-panel stargate
jumps between them and used it **zero** times.

**Widening the search to include `Jump` is the wrong fix**, which is why this is
a parse. The Selected Item panel carries its own `Jump` button -- #170's
`selectedItemJump` -- so a whole-tree search for that word collides with it on
the first reading with no way to tell which was clicked. Matching the widget's
own *type* name inside a `DungeonInfoPanelEntry` cannot reach that panel at all,
and `test_the_selected_item_panels_own_jump_is_not_the_trackers` is the case.

Three rules decide whether a label is a step, and each excludes a different
failure:

  - `travelLabelIsReadableText` (#92) -- run 11 rendered a travel step as six C0
    control characters around one unassigned codepoint and run 22 as a distance
    wrapped in NULs, and accepting either is the only way this change could send
    a ship somewhere nobody asked for;
  - `travelLabelIsACommand` -- `Warping`, `Jumping` and `Docking` are the client
    saying the trip is already happening, and clicking one is #99's
    re-commanded run-in with a different button. It is an **allow-list**, so a
    word the client invents next leaves the bot behaving as it did before;
  - the parser's `_display` filter -- the chain hides the tasks that are not
    available rather than removing them, and run 14 on the other bot sat docked
    for 750 readings because a rule could not see the one that was.

**#280: the tracker draws two task rows and the type-name prefix reached one.**
The chain's `task_container_travel_to_location` row carries `Set Destination` and
`Jump` on a `TravelToLocationButtonTask...` widget; the row that gets the ship
*into* the site carries `Warp to Site` on a `TravelStateButtonTaskWidget`, which
does not start with that prefix, so `travelButton` was `Nothing` for it on every
reading while the client drew the button. The selector is a union now -- the same
prefix, plus the client's own `_name` for each of the two objective tasks -- and
`TheEnteringRowIsReadToo` is where the cases that fail against the unchanged
parser live. `TheSelectorIsReadOutOfTheParser` is what refuses the widening the
issue rules out, and `BothRowsDisplayedAtOnce` records the one shape nobody has
read rather than guessing at it.

**#291: that name is the row's progress bar's too, and the bar sorts first.**
Widening the selector to reach the enter-dungeon row's button made the
travelling row's unreachable -- run 48 read
`ProgressBarTaskWidget _name=objective_task_travel_to_location
'8 jumps | 0.6 Andabiar'` ahead of the button carrying `Set Destination`,
neither with `_display`, so `List.head` took the bar. The parse prefers a
button among the admitted candidates now and keeps `List.head` for the
no-button case. `TheProgressBarSharesTheButtonsName` is where the cases that
fail against the unchanged parser live, and it is also the correction to
`BothRowsDisplayedAtOnce`: that class was the guard for "two candidates at
once" and anticipated two *buttons*, where the ambiguity that arrived is a
button and a widget nobody can press.

**#147's ordering is untouched and is asserted here as well as next door**: an
acceleration gate in reach still outranks the tracker button, because a gate is
progress inside the site and the button is how the ship reaches the next one.

The rules are executed through the real `Bot.elm` in `elm repl` and the readings
they are asked about are built by the real `EveOnline.ParseUserInterface`. What
is not an expression -- the old search's absence, the wiring -- is read out of
the source through a whitespace-collapsing reader.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_gate_panel_button import (
    EVE_BOT_LOGS, read_log, reading, saxrat_runs, selected_item_window)
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SAXRAT_DIR, SaxratRepl, body_of, collapsed,
    node, source_of)

SAXRAT_PARSER_ELM = os.path.join(SAXRAT_DIR, "EveOnline", "ParseUserInterface.elm")

# The client's own type names for the tracker's entry and its travel widget.
# `DungeonInfoPanelEntry` is what the Opportunities panel calls an escalation.
ENTRY_TYPE = "DungeonInfoPanelEntry"

# Two spellings of the same slot have been read on this client: run 26 recorded
# the first and a later live read the second. Whether that is a client change or
# a second node in the same chain is unresolved, which is why the matcher is a
# prefix rather than either literal.
TRAVEL_WIDGET_TYPES = ("TravelToLocationButtonTaskWidget",
                       "TravelToLocationButtonTask")

# The client's own `_name` for each of the objective chain's two travel tasks,
# and the widget type each has been read on. Both come from #280's capture of
# the live client during run `saxrat_20260816-173606`.
TRAVEL_TASK_NAME = "objective_task_travel_to_location"
ENTER_TASK_NAME = "objective_task_enter_dungeon"

# The type the *entering* row carries. It does not begin with
# `TravelToLocationButtonTask`, which is the whole of #280.
ENTER_WIDGET_TYPE = "TravelStateButtonTaskWidget"

# What the entering row was drawn with in that capture.
ENTER_LABEL = "Warp to Site"

# #291: the widget that shares `TRAVEL_TASK_NAME` with the travelling row's
# button and is listed ahead of it. It is not a button and nothing can press it.
BAR_WIDGET_TYPE = "ProgressBarTaskWidget"

# The bar's two cells, as the client draws them -- **separate labels** under one
# widget. `eve_repl` prints them joined by ` | `, and a fixture built from that
# line carries the join rather than the structure: the destination parse matches
# each cell on its own shape and reads nothing from a single string.
BAR_JUMPS = "8 jumps"
BAR_DESTINATION = "0.6 Andabiar"

# What run 48 read on it, as the repl joined it. `travelLabelIsACommand` refuses
# it and `travelLabelIsReadableText` accepts it, which is the whole of why the
# failure was a stand-down rather than a wrong click.
BAR_LABEL = "%s | %s" % (BAR_JUMPS, BAR_DESTINATION)

SITE_NAME = "Sansha's Command Relay Outpost"

# Every label anybody has read off this slot, sorted the way the branch sorts
# them. `Warp to Location` and `Dock` come from the mission runner's own
# vocabulary for the same widget type; `Dock` has never been read off the
# tracker and is carried on that separation rather than on an observation here.
#
# `Undock` joined them in #313, which is the change
# `test_the_entering_row_wins_nothing_the_allow_list_refuses` already describes:
# #280 had it under "Not this" as a state read while the ship was undocking, and
# it was then read off the live client as what this widget renders while the ship
# is docked in the escalation's own system -- a command, and the one that gets
# the ship out of a station it parked in. That case was written to keep `Undock`
# out of `STATE_LABELS` so it would not go red on a change that is right; this
# list is the other half of the same move and was missed.
COMMAND_LABELS = ["Set Destination", "Jump", "Warp to Site",
                  "Warp to Location", "Dock", "Undock"]

# The states. Clicking one re-commands a trip already under way.
STATE_LABELS = ["Warping", "Jumping", "Docking", "Preparing", "Undocking",
                "Destination Set", "Abort Undock"]

# Words the tracker really does render that are not a trip at all. `View
# Details` is on the collapsed escalations in the capture this was written from,
# which is what makes the allow-list discriminating rather than decorative.
LABELS_THAT_ARE_NOT_A_TRIP = ["View Details", "Read Details",
                              "Start Conversation", "Travel to Location"]

# The two non-text labels the mission runner's corpus holds, as the codepoints
# the logs carry. Neither can be written as an Elm string literal.
NON_TEXT_LABELS = {
    "run 11's glyph": [0x02, 0x00, 0xAD1D8, 0x01, 0x01, 0x00, 0x01],
    "run 22's NUL-wrapped distance": [
        0x00, 0x00, 0x2E, 0x35, 0x30, 0x20, 0x41, 0x55, 0x00],
}

# The decision line the old whole-tree search printed. Recorded logs carry it;
# nothing new does, so it is only ever matched against `~/eve-bot-logs`.
OLD_OPPORTUNITY_LINE = "opportunity -- warp there"

# What a route-panel stargate jump prints, which is the long way round the
# tracker exists to replace.
STARGATE_JUMP_LINE = "Jump through"


def every_saxrat_run():
    """Every recorded saxrat run this machine has, by number.

    Globbed rather than listed, so a run 53 is read without an edit -- the
    relation below is about what the corpus can and cannot say, and pinning it
    to run numbers is how a growing corpus turns a true claim red.
    """
    try:
        names = os.listdir(EVE_BOT_LOGS)
    except OSError:
        names = []
    numbers = sorted(int(match.group(1)) for match in
                     (re.match(r"saxrat_run(\d+)\.log$", name)
                      for name in names) if match)
    return saxrat_runs(*numbers)


def tracker_offers(path):
    """Every label the tracker's own decision line named, streamed.

    Streamed rather than read whole because this reads the entire saxrat corpus
    and the largest single log on this machine is measured in hundreds of
    megabytes.
    """
    pattern = re.compile(r"The Opportunities tracker offers '([^']*)'")
    labels = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = pattern.search(line)
            if match:
                labels.append(match.group(1))
    return labels


def let_binding_by_indentation(source, declaration_name, name):
    """One `let` binding of a declaration, sliced by indentation.

    A reader that ends at the next ` <name> = ` stops inside a `case` or a
    record literal, and #291's own binding is a `case`, so an assertion about
    its second branch would read text that stopped at the first. This takes the
    line the binding opens on and ends at the next non-blank line indented no
    further -- the correction PRs #147, #156 and #159 each made once.

    Comments are dropped before anything is asserted on the result: the doc
    comment over this binding names every identifier the cases below look for,
    so a version that had deleted the code and kept the paragraph would pass.
    """
    lines = body_of(source, declaration_name).splitlines()
    opens = [index for index, line in enumerate(lines)
             if re.match(r"^(\s*)%s =(\s|$)" % re.escape(name), line)]
    assert opens, "no let binding named %r" % name
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            end = index
            break
    without_comments = [re.sub(r"--.*$", "", line) for line in lines[start:end]]
    return collapsed("\n".join(without_comments))


def string_from_codepoints(codepoints):
    """A label a string literal cannot carry, rebuilt inside Elm.

    `Char.fromCode` takes a NUL and a lone unassigned codepoint where a literal
    cannot, so nothing is escaped and nothing is lost in transit.
    """
    return "String.fromList (List.map Char.fromCode [ %s ])" % ", ".join(
        str(codepoint) for codepoint in codepoints)


def travel_button(text, type_name=TRAVEL_WIDGET_TYPES[0], displayed=True,
                  named_label=True, with_region=True,
                  task_name=TRAVEL_TASK_NAME):
    """The tracker's travel widget, as the client draws it.

    `_display` False **with** a region is the case worth building: a widget the
    parser's region walk drops on its own proves nothing about the display
    filter, so the hidden fixtures here keep their region.

    `task_name` is the client's own `_name` for the objective task the widget
    belongs to. `None` builds one carrying no name at all, which is what makes
    "the type-name prefix still carries the travelling row on its own" a claim
    a case can put rather than one the fixture satisfies twice over.
    """
    entries = {} if task_name is None else {"_name": task_name}
    if not displayed:
        entries["_display"] = False
    label_entries = {"_setText": text}
    if named_label:
        label_entries["_name"] = "label"
    return node(type_name, entries, [
        node("EveLabelMedium", label_entries, region=(99, 486, 120, 16)),
        node("ButtonUnderlay", {}, region=(99, 486, 217, 21)),
    ], region=(99, 486, 217, 21) if with_region else None)


def expanded_entry(buttons, site_name=SITE_NAME):
    """One escalation with its objective chain open, which is the only state
    that carries a button at all.

    The nesting is the capture's: entry -> chain -> objective -> the widget.
    """
    children = [node("EveLabelLarge", {"_setText": site_name},
                     region=(91, 376, 200, 18))]
    if site_name is None:
        children = []
    children.append(
        node("ObjectiveChainEntry", {"_name": "objective_chain_55"}, [
            node("ObjectiveEntry", {"_name": "objective_enter_dungeon"}, [
                node("ContainerAutoSize", {"_name": "buttons_container"},
                     buttons, region=(86, 389, 217, 25)),
            ], region=(79, 330, 231, 91)),
        ], region=(79, 330, 231, 91)))
    return node(ENTRY_TYPE, {"_name": "escalation_sites:50791"}, children,
                region=(79, 298, 231, 123))


def enter_button(text=ENTER_LABEL, **kwargs):
    """The row that enters the site: a `TravelStateButtonTaskWidget`.

    #280's whole subject. Its type name does not begin with
    `TravelToLocationButtonTask`, so the prefix that reached the travelling row
    answered `Nothing` for this one on every reading.
    """
    kwargs.setdefault("type_name", ENTER_WIDGET_TYPE)
    kwargs.setdefault("task_name", ENTER_TASK_NAME)
    return travel_button(text, **kwargs)


def progress_bar(jumps=BAR_JUMPS, destination=BAR_DESTINATION,
                 task_name=TRAVEL_TASK_NAME, displayed=True):
    """The travelling row's progress bar, under the button's own `_name`.

    #291's whole subject: admitted by the `_name` half of the selector, listed
    ahead of the button, and nothing can press it.

    **Two labels, not one string**, which is the correction this fixture took
    when the 0.5 destination gate started reading it. The live capture prints
    `8 jumps | 0.6 Andabiar` and that pipe is `eve_repl` joining two separate
    texts rather than anything the client wrote. Built with one label the
    fixture is a tree the client never produces, and the destination parse --
    matching each cell on its own shape -- correctly reads nothing from it.

    No `_display` key on either this or the button, since run 48's capture shows
    `_display=None` on both, so the only thing separating the two fixtures is
    the widget's type name -- which is what the selection reads.
    """
    entries = {"_name": task_name} if task_name is not None else {}
    if not displayed:
        entries["_display"] = False
    cells = [text for text in (jumps, destination) if text is not None]
    return node(BAR_WIDGET_TYPE, entries,
                [node("EveLabelMedium", {"_setText": text},
                      region=(99, 460, 120, 16)) for text in cells],
                region=(99, 460, 217, 21))


def capture_entry(buttons, site_name=SITE_NAME,
                  title="Travel to Location", task_containers=True):
    """The escalation exactly as #280 read it off the live client.

    Nested as the capture is rather than as `expanded_entry` flattens it --
    `content_container`, the chain, the objective, `task_container` and its
    three children, the buttons under the last of them. The two empty
    `task_container_*` rows are carried because they are what the client's own
    names for the two tasks are read from, and because a selector keyed on the
    *container* names rather than on the widgets' would pass without them.

    Note the entry's own title reads `Travel to Location` while the live button
    is the enter-dungeon one, which is why nothing here picks a task by title.
    """
    chain_children = []
    if title is not None:
        chain_children.append(
            node("EveLabelLarge", {"_name": "title", "_setText": title},
                 region=(86, 350, 200, 18)))
    containers = []
    if task_containers:
        containers = [
            node("ContainerAutoSize",
                 {"_name": "task_container_travel_to_location"}, [],
                 region=(86, 370, 217, 1)),
            node("ContainerAutoSize",
                 {"_name": "task_container_enter_dungeon"}, [],
                 region=(86, 371, 217, 1)),
        ]
    chain_children.append(
        node("ContainerAutoSize", {"_name": "task_container"},
             containers + [
                 node("ContainerAutoSize", {"_name": "buttons_container"},
                      buttons, region=(86, 389, 217, 25)),
             ], region=(86, 370, 217, 45)))
    children = []
    if site_name is not None:
        children.append(node("EveLabelLarge", {"_setText": site_name},
                             region=(91, 376, 200, 18)))
    children.append(
        node("ContainerAutoSize", {"_name": "content_container"}, [
            node("ObjectiveChainEntry", {"_name": "objective_chain_55"}, [
                node("ObjectiveEntry", {"_name": "objective_enter_dungeon"},
                     chain_children, region=(79, 330, 231, 91)),
            ], region=(79, 330, 231, 91)),
        ], region=(79, 320, 231, 101)))
    return node(ENTRY_TYPE, {"_name": "escalation_sites:50839662"}, children,
                region=(79, 298, 231, 123))


def collapsed_entry(site_name=SITE_NAME):
    """A further escalation, 31px tall against the expanded one's 123.

    It offers its name and `View Details` and no travel widget, which is what
    makes "act on the expanded one" a choice the client has already made rather
    than an index into a list that reorders.
    """
    return node(ENTRY_TYPE, {"_name": "escalation_sites:50792"}, [
        node("EveLabelLarge", {"_setText": site_name}, region=(91, 526, 200, 18)),
        node("EveLabelMedium", {"_setText": "View Details"},
             region=(91, 540, 100, 14)),
    ], region=(91, 526, 231, 31))


def tracker(entries):
    """The Opportunities panel holding them."""
    return node("InfoPanelJobBoard", {"_name": "l_jobBoard"}, [
        node("EveLabelLarge", {"_setText": "Opportunities"},
             region=(29, 231, 120, 18)),
    ] + entries, region=(29, 231, 240, 420))


def selected_item_panel_offering_jump():
    """The Selected Item panel with its own `Jump`, read live at (1517,142).

    This is the button `selectedItemJump` presses, and the whole reason the
    tracker is reached by type name rather than by a word.
    """
    return selected_item_window("Tar", buttons=["selectedItemJump"])


class TrackerRepl(SaxratRepl):
    """saxrat's harness, plus the module a decision line has to be unpacked with.

    `Bot exposing (..)` does not re-export `Common.DecisionPath`, and the
    branch's wording is rendered rather than asserted by substring over the
    source -- which is how a case written to catch a press aimed at the wrong
    button once passed on the branch's own log text (#145).
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", PREAMBLE + ("import Common.DecisionPath",))
        super().__init__(**kwargs)


class TheParserReadsTheTrackersOwnButton(unittest.TestCase):
    """`EveOnline.ParseUserInterface`, over the shapes the client draws.

    Neither app parsed `TravelToLocationButtonTaskWidget` or
    `DungeonInfoPanelEntry` before this; the mission runner reaches its own
    equivalent by a type-name search and saxrat's copy had no counterpart.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def entry_field(self, children, field):
        return self.repl.strings([
            "reading"
            " |> Maybe.map (.opportunityInfoPanelEntries >> List.filterMap"
            " .travelButton >> List.filterMap %s >> List.head)"
            " |> Maybe.withDefault Nothing"
            " |> Maybe.withDefault \"<none>\"" % field],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def travel_label(self, children):
        return self.entry_field(children, ".label")

    def site_names(self, children):
        return self.repl.strings([
            "reading"
            " |> Maybe.map (.opportunityInfoPanelEntries"
            " >> List.filterMap .siteName >> String.join \"|\")"
            " |> Maybe.withDefault \"<no reading>\""],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def entry_count(self, children):
        return self.repl.strings([
            "reading"
            " |> Maybe.map (.opportunityInfoPanelEntries >> List.length"
            " >> String.fromInt)"
            " |> Maybe.withDefault \"<no reading>\""],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_the_button_is_read_with_the_label_the_client_put_on_it(self):
        """Run 26's own shape, which used to parse as nothing at all."""
        for label_text in COMMAND_LABELS + STATE_LABELS:
            with self.subTest(label=label_text):
                self.assertEqual(
                    self.travel_label(
                        [tracker([expanded_entry([travel_button(label_text)])])]),
                    label_text)

    def test_both_spellings_of_the_widget_are_read(self):
        """Run 26 recorded one and a later live read the other."""
        for type_name in TRAVEL_WIDGET_TYPES:
            with self.subTest(type_name=type_name):
                self.assertEqual(
                    self.travel_label([tracker([expanded_entry(
                        [travel_button("Jump", type_name=type_name)])])]),
                    "Jump")

    def test_a_hidden_widget_is_not_offered(self):
        """`_display` False with a region -- the case the region walk misses.

        This is the display filter doing the selecting rather than guarding.
        """
        self.assertEqual(
            self.travel_label([tracker([expanded_entry(
                [travel_button("Jump", displayed=False)])])]),
            "<none>")

    def test_a_displayed_widget_beside_a_hidden_one_is_the_one_taken(self):
        """Which one is shown is the client saying which task is live."""
        self.assertEqual(
            self.travel_label([tracker([expanded_entry([
                travel_button("Set Destination", displayed=False),
                travel_button("Jump"),
            ])])]),
            "Jump")

    def test_a_collapsed_escalation_offers_no_button(self):
        """The button exists only under the entry the client has expanded."""
        self.assertEqual(
            self.travel_label([tracker([collapsed_entry()])]), "<none>")

    def test_the_expanded_entry_is_the_one_with_a_button_among_several(self):
        """Five escalations in the panel, one of them open.

        "Which escalation" is answered by the client rather than by position:
        a button belonging to a collapsed one is not in the tree to be clicked.
        """
        children = [tracker(
            [collapsed_entry(), expanded_entry([travel_button("Jump")]),
             collapsed_entry(), collapsed_entry()])]
        self.assertEqual(self.entry_count(children), "4")
        self.assertEqual(self.travel_label(children), "Jump")

    def test_the_escalations_name_is_read_for_the_decision_line(self):
        self.assertEqual(
            self.site_names([tracker([expanded_entry(
                [travel_button("Jump")], site_name=SITE_NAME)])]),
            SITE_NAME)

    def test_a_label_the_client_did_not_name_is_still_read(self):
        """The tracker capture records an `EveLabelMedium` and not its `_name`.

        Requiring `_name = "label"` would answer `Nothing` for a button the
        client is plainly labelling, so the named label wins where there is one
        and any text under the button is the fallback.
        """
        self.assertEqual(
            self.travel_label([tracker([expanded_entry(
                [travel_button("Jump", named_label=False)])])]),
            "Jump")

    def test_the_selected_item_panels_own_jump_is_not_the_trackers(self):
        """The collision a widened text search would have made on reading one.

        #170's button, read live at canvas (1517,142) in the same reading as the
        tracker. Nothing about it is inside a `DungeonInfoPanelEntry`, so a
        type-name match cannot reach it -- and this is the case that says so
        rather than the argument.
        """
        self.assertEqual(
            self.travel_label([selected_item_panel_offering_jump()]), "<none>")
        self.assertEqual(
            self.entry_count([selected_item_panel_offering_jump()]), "0")

    def test_a_reading_with_no_tracker_at_all_reads_as_none(self):
        self.assertEqual(self.entry_count(reading()), "0")

    def test_the_fixture_carries_the_label_the_client_wrote(self):
        """#174's discipline, and the reason the fail-closed cases mean anything.

        A reading that never decoded and a rule that declined it are the same
        answer from outside, so the non-text labels are asserted to reach the
        parser **intact** before anything concludes that the branch refused
        them. Compared inside Elm, since the repl escapes a control character
        on its way out and `\\0` and the two characters `\\` `0` would print
        alike.
        """
        for name, codepoints in sorted(NON_TEXT_LABELS.items()):
            with self.subTest(label=name):
                text = "".join(chr(codepoint) for codepoint in codepoints)
                children = [tracker([expanded_entry([travel_button(text)])])]
                self.assertEqual(self.repl.evaluate([
                    "reading"
                    " |> Maybe.map (.opportunityInfoPanelEntries"
                    " >> List.filterMap .travelButton"
                    " >> List.filterMap .label"
                    " >> List.member (%s))"
                    " |> Maybe.withDefault False"
                    % string_from_codepoints(codepoints)],
                    definitions=[
                        TrackerRepl.reading_binding("reading", children)])[0],
                    True,
                    "the fixture did not reach the parser, so nothing a case "
                    "concludes from it is about the rule")


class TheLabelRuleSeparatesCommandsFromStates(unittest.TestCase):
    """`travelLabelIsACommand` and `travelLabelIsReadableText`, executed.

    Both are asked directly rather than only end to end, because the allow-list
    subsumes the readable-text test for every input either has been shown -- so
    an end-to-end case over a garbage label would pass with the readable-text
    clause removed, and only these can say the clause answers for itself.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def is_command(self, expressions):
        return self.repl.evaluate(
            ["travelLabelIsACommand (%s)" % expression
             for expression in expressions])

    def is_readable(self, expressions):
        return self.repl.evaluate(
            ["travelLabelIsReadableText (%s)" % expression
             for expression in expressions])

    @staticmethod
    def literal(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def test_every_command_label_is_a_step(self):
        answers = self.is_command([self.literal(text) for text in COMMAND_LABELS])
        self.assertEqual(answers, [True] * len(COMMAND_LABELS),
                         dict(zip(COMMAND_LABELS, answers)))

    def test_no_state_label_is_a_step(self):
        """The whole of #99 here: one click on `Warping` re-commands the trip."""
        answers = self.is_command([self.literal(text) for text in STATE_LABELS])
        self.assertEqual(answers, [False] * len(STATE_LABELS),
                         dict(zip(STATE_LABELS, answers)))

    def test_a_word_that_is_not_a_trip_is_not_a_step(self):
        """`View Details` is on the collapsed escalations in the capture.

        This is what separates an allow-list from a list of states to refuse: a
        deny-list fires on every word the client's vocabulary grows next.
        """
        answers = self.is_command(
            [self.literal(text) for text in LABELS_THAT_ARE_NOT_A_TRIP])
        self.assertEqual(answers, [False] * len(LABELS_THAT_ARE_NOT_A_TRIP),
                         dict(zip(LABELS_THAT_ARE_NOT_A_TRIP, answers)))

    def test_a_command_word_inside_a_longer_label_is_not_a_step(self):
        """The equality is what makes the list safe to write in five words.

        A substring test would take `Dock` out of `Dock in Station` and `Jump`
        out of `Jump Through Stargate`, which is the route panel's menu entry.
        """
        for text in ["Dock in Station", "Jump Through Stargate",
                     "Set Destination and Undock", "Warp to Site 2"]:
            with self.subTest(label=text):
                self.assertEqual(self.is_command([self.literal(text)]), [False])

    def test_the_client_may_change_its_capitalisation_or_padding(self):
        for text in ["  Jump  ", "jump", "JUMP", "Warp To Site"]:
            with self.subTest(label=text):
                self.assertEqual(self.is_command([self.literal(text)]), [True])

    def test_neither_non_text_label_is_a_step(self):
        names = sorted(NON_TEXT_LABELS)
        answers = self.is_command(
            [string_from_codepoints(NON_TEXT_LABELS[name]) for name in names])
        self.assertEqual(answers, [False] * len(names), dict(zip(names, answers)))

    def test_neither_non_text_label_reads_as_text(self):
        """#92, asked of the clause that owns it.

        Run 11's is six C0 controls around one codepoint that is *unassigned*
        rather than private-use, which is the trap a PUA test falls into; run
        22's is a distance with NULs around it, so it has letters and is still
        not a label.
        """
        names = sorted(NON_TEXT_LABELS)
        answers = self.is_readable(
            [string_from_codepoints(NON_TEXT_LABELS[name]) for name in names])
        self.assertEqual(answers, [False] * len(names), dict(zip(names, answers)))

    def test_every_label_the_client_has_written_reads_as_text(self):
        """The other direction, so a rule refusing everything cannot pass."""
        texts = COMMAND_LABELS + STATE_LABELS + LABELS_THAT_ARE_NOT_A_TRIP
        answers = self.is_readable([self.literal(text) for text in texts])
        self.assertEqual(answers, [True] * len(texts), dict(zip(texts, answers)))

    def test_an_empty_or_blank_label_is_neither(self):
        for text in ["", "   "]:
            with self.subTest(label=text):
                self.assertEqual(self.is_readable([self.literal(text)]), [False])
                self.assertEqual(self.is_command([self.literal(text)]), [False])

    def test_a_label_with_no_letter_in_it_is_not_text(self):
        for text in [".50", "---", "12"]:
            with self.subTest(label=text):
                self.assertEqual(self.is_readable([self.literal(text)]), [False])


class TheBranchActsOnWhatTheTrackerOffers(unittest.TestCase):
    """`warpToOpportunitySiteIfAvailable`, end to end on real parsed readings.

    Every fixture goes through `EveOnline.MemoryReading` and the real parser, so
    what is asserted is what the bot would have been handed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def offers_a_step(self, children):
        return self.repl.evaluate([
            "reading"
            " |> Maybe.map (\\r -> warpToOpportunitySiteIfAvailable r /= Nothing)"
            " |> Maybe.withDefault False"],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_a_command_label_is_taken(self):
        for text in COMMAND_LABELS:
            with self.subTest(label=text):
                self.assertTrue(self.offers_a_step(
                    [tracker([expanded_entry([travel_button(text)])])]),
                    "the tracker offered %r and the branch declined it" % text)

    def test_a_state_label_is_not_taken(self):
        """Run 5's own state, answered off the panel this time.

        The old search answered `Just` here for 3,458 readings because the
        button stays drawn after arrival; the label says `Warping` and this
        declines.
        """
        for text in STATE_LABELS:
            with self.subTest(label=text):
                self.assertFalse(self.offers_a_step(
                    [tracker([expanded_entry([travel_button(text)])])]),
                    "the branch acted on %r, which is a trip already under way"
                    % text)

    def test_an_unreadable_label_is_not_taken(self):
        """#92's two labels, carried through the fixture as the client wrote them.

        A NUL and a lone astral codepoint both survive `elm_json_literal`, since
        the inner `json.dumps` turns each into a `\\uXXXX` escape the JSON
        decoder reads back -- so the parser is handed the label the client
        rendered rather than a stand-in for it, and the branch is asked the real
        question. `TheFixtureCarriesTheLabelTheClientWrote` is what says the
        round trip happened, since a fixture that never arrived and a label the
        branch declines are the same answer from here.
        """
        for name, codepoints in sorted(NON_TEXT_LABELS.items()):
            with self.subTest(label=name):
                text = "".join(chr(codepoint) for codepoint in codepoints)
                self.assertFalse(
                    self.offers_a_step(
                        [tracker([expanded_entry([travel_button(text)])])]),
                    "the branch acted on a label the client failed to render")

    def test_a_hidden_task_is_not_taken(self):
        """Run 14's shape: the step is rendered, and hidden, so it is not live."""
        self.assertFalse(self.offers_a_step(
            [tracker([expanded_entry([travel_button("Jump", displayed=False)])])]))

    def test_a_tracker_offering_nothing_is_not_a_step(self):
        self.assertFalse(self.offers_a_step([tracker([collapsed_entry()])]))

    def test_the_selected_item_panels_jump_is_not_a_step(self):
        """The whole-tree search's collision, asserted as an absence.

        `findUiElementWithText "Jump"` would have found this on reading one.
        """
        self.assertFalse(self.offers_a_step([selected_item_panel_offering_jump()]))

    def test_a_reading_with_no_tracker_is_not_a_step(self):
        self.assertFalse(self.offers_a_step(reading()))

    def test_the_line_names_the_label_and_the_escalation(self):
        """So a log says which of four steps was taken and for which site."""
        line = self.repl.strings([
            "reading"
            " |> Maybe.andThen warpToOpportunitySiteIfAvailable"
            " |> Maybe.map (Common.DecisionPath"
            ".unpackToDecisionStagesDescriptionsAndLeaf >> Tuple.first"
            " >> String.join \" | \")"
            " |> Maybe.withDefault \"<no step>\""],
            definitions=[TrackerRepl.reading_binding(
                "reading",
                [tracker([expanded_entry([travel_button("Jump")])])])])[0]
        self.assertIn("Jump", line)
        self.assertIn(SITE_NAME, line)

    def test_an_escalation_with_no_name_still_offers_its_step(self):
        """The name is for the log line and decides nothing."""
        self.assertTrue(self.offers_a_step(
            [tracker([expanded_entry([travel_button("Jump")], site_name=None)])]))


class TheGateStillOutranksTheTracker(unittest.TestCase):
    """#147's ordering, asked of a reading that offers both.

    The tracker's button is how the ship reaches the *next* site; an
    acceleration gate on the overview means it has already arrived at one, and
    that work comes first. The rule is `siteProgressStep` and this ordering
    within it is unchanged -- what this asserts is that the new branch has not
    been wired around it.

    The scanner window is held **closed** throughout, which is the state that
    leaves the tracker's step reachable at all; the gate clause is what these
    cases are about, and it applies in either state.

    Every fixture here offers `Jump`, which since #261 matters: an *arrival*
    label is asked above the gate now and a travelling one is not, so these
    cases are about the half of #147's ordering that is unchanged. The
    reversal has its own file.
    """

    STEPS = ("WorkTheAccelerationGate", "WarpToTheOpportunitySite",
             "HuntWithTheProbeScanner")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)
        cls.source = source_of(SAXRAT_BOT_ELM)

    def step_for(self, children):
        """The ordering, resolved against a reading the real parser produced."""
        answers = self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> siteProgressStep"
             " { gateBranchOffersAStep = False"
             " , arrivalIsOffered ="
             " (opportunityTravelStep r |> Maybe.map (.label >>"
             " opportunityLabelArrivesAtTheSite) |> Maybe.withDefault False)"
             " , warpToSiteIsOffered ="
             " warpToOpportunitySiteIfAvailable r /= Nothing"
             " , gateWithinReach = accelerationGateIsWithinReach r"
             " , probeScannerWindowIsClosed = True"
             " } == %s) |> Maybe.withDefault False" % step
             for step in self.STEPS],
            definitions=[TrackerRepl.reading_binding("reading", children)])
        chosen = [step for step, yes in zip(self.STEPS, answers) if yes]
        self.assertEqual(len(chosen), 1,
                         "expected exactly one step, got %s" % chosen)
        return chosen[0]

    def test_a_tracker_step_offered_beside_a_gate_in_reach_is_declined(self):
        """Run 5's grid, now with a label on the button as well."""
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker([expanded_entry([travel_button("Jump")])])]),
            "HuntWithTheProbeScanner")

    def test_the_same_step_with_no_gate_in_reach_is_taken(self):
        """Stated as the comparison, which only an ordering can satisfy."""
        self.assertEqual(
            self.step_for(reading(gate_distance="40 km")
                          + [tracker([expanded_entry([travel_button("Jump")])])]),
            "WarpToTheOpportunitySite")

    def test_the_ordering_still_goes_through_the_shared_rule(self):
        binding = collapsed(body_of(self.source, "siteProgressStepOrElse"))
        self.assertIn("case siteProgressStep {", binding)
        self.assertIn(
            "opportunityWarpStep = warpToOpportunitySiteIfAvailable"
            " (escalationEntriesPermitted context.eventContext.botSettings"
            " context.readingFromGameClient)", collapsed(self.source),
            "the warp step no longer narrows the reading first, so a lowsec "
            "escalation reaches the ordering")
        self.assertIn(
            "gateWithinReach = accelerationGateIsWithinReach"
            " context.readingFromGameClient", binding)


class TheWholeTreeSearchIsGone(unittest.TestCase):
    """Read out of the source, because an absence is not an expression.

    The search is what #147 measured and what a revert would restore, and the
    parse is what makes the tracker reachable at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.parser = source_of(SAXRAT_PARSER_ELM)
        cls.branch = collapsed(body_of(cls.source, "opportunityTravelStep"))

    def test_the_branch_no_longer_text_searches_the_tree(self):
        self.assertNotIn('findUiElementWithText "Warp to Site"',
                         collapsed(self.source))

    def test_no_rule_text_searches_for_jump_either(self):
        """The widening the issue rules out, asserted rather than trusted."""
        self.assertNotIn('findUiElementWithText "Jump"', collapsed(self.source))

    def test_the_step_is_read_off_the_parsed_tracker(self):
        self.assertIn("readingFromGameClient.opportunityInfoPanelEntries",
                      self.branch)

    def test_the_step_consults_the_label_rule(self):
        self.assertIn("travelLabelIsACommand", self.branch)

    def test_the_command_rule_asks_the_readable_text_rule_first(self):
        rule = collapsed(body_of(self.source, "travelLabelIsACommand"))
        self.assertIn("travelLabelIsReadableText label", rule)
        self.assertIn("opportunityTravelCommandLabels |> List.member", rule)

    def test_the_command_list_is_exactly_the_listed_words(self):
        """Named for the property rather than for a count.

        It was `..._is_the_five_words_and_no_more` until `Undock` made them six,
        and a name carrying the number goes stale on exactly the change this
        case exists to notice -- while still passing, so the staleness is
        invisible.
        """
        listed = collapsed(body_of(self.source, "opportunityTravelCommandLabels"))
        for text in COMMAND_LABELS:
            self.assertIn('"%s"' % text.lower(), listed)
        self.assertEqual(len(re.findall(r'"', listed)), 2 * len(COMMAND_LABELS),
                         "the command list has grown or shrunk: %s" % listed)

    def test_the_parser_matches_the_widget_by_type_name_or_task_name(self):
        """Which is what scopes it to the tracker and away from #170's button.

        This case pinned the bare `String.startsWith` inside the parse until
        #280, and the prefix on its own is what could not see the entering row.
        The selector moved into `uiNodeIsOpportunityTravelTask`, so the pin
        follows it there rather than being deleted -- what must not come back is
        a match that reaches the Selected Item panel.
        """
        parse = collapsed(body_of(self.parser, "parseOpportunityInfoPanelEntry"))
        self.assertIn("uiNodeIsOpportunityTravelTask", parse)
        self.assertIn("nodeIsDisplayedFromDictEntries", parse)
        selector = collapsed(
            body_of(self.parser, "uiNodeIsOpportunityTravelTask"))
        self.assertIn("String.startsWith opportunityTravelTaskTypePrefix",
                      selector)
        self.assertIn("List.member name opportunityTravelTaskNames", selector)

    def test_the_parser_finds_entries_by_the_clients_own_type_name(self):
        finder = collapsed(
            body_of(self.parser, "parseOpportunityInfoPanelEntriesFromUITreeRoot"))
        self.assertIn('(==) "%s"' % ENTRY_TYPE, finder)

    def test_an_absent_display_key_still_means_shown(self):
        """The overview's own rows carry none while plainly on screen."""
        helper = re.search(
            r"nodeIsDisplayedFromDictEntries uiNode =.*?Maybe\.withDefault (\w+)",
            self.parser, re.S)
        self.assertIsNotNone(helper)
        self.assertEqual("True", helper.group(1))


class TheEnteringRowIsReadToo(unittest.TestCase):
    """#280: the row that gets the ship into the site, through the real parser.

    Every fixture here is the capture's own nesting -- `content_container`, the
    chain, the objective, `task_container` with its three children -- and the
    labels are the ones the client wrote. What separates these cases from the
    ones above is the widget's **type**: `TravelStateButtonTaskWidget` does not
    begin with `TravelToLocationButtonTask`, so before this change the parser
    answered `Nothing` for it however plainly the client drew it.

    The counts behind that are one run's: 62 travel steps taken off the first
    row and zero off this one, over a session that crossed six systems to reach
    a site it then never entered. That run is not on this machine, so nothing
    here recounts it; what the local corpus can say is in
    `TheRecordedSaxratRunsTest`.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def travel_label(self, children):
        return TheParserReadsTheTrackersOwnButton.travel_label(self, children)

    def entry_field(self, children, field):
        return TheParserReadsTheTrackersOwnButton.entry_field(
            self, children, field)

    def offers_a_step(self, children):
        return TheBranchActsOnWhatTheTrackerOffers.offers_a_step(self, children)

    def test_the_warp_to_site_button_is_found_where_it_was_not(self):
        """The capture in its own nesting. `Nothing` before #280."""
        self.assertEqual(
            self.travel_label([tracker([capture_entry([enter_button()])])]),
            ENTER_LABEL)

    def test_the_branch_takes_it(self):
        """`warpToOpportunitySiteIfAvailable` answered `Nothing` for this."""
        self.assertTrue(
            self.offers_a_step([tracker([capture_entry([enter_button()])])]),
            "the tracker drew 'Warp to Site' and the branch declined it")

    def test_the_travelling_row_is_still_found(self):
        """The half that must not be traded away.

        Built with **no** `_name` at all, so only the type-name prefix can admit
        it -- a selector that had dropped the prefix and kept the two task names
        would pass a fixture carrying both and fail here.
        """
        for type_name in TRAVEL_WIDGET_TYPES:
            with self.subTest(type_name=type_name):
                self.assertEqual(
                    self.travel_label([tracker([capture_entry([travel_button(
                        "Jump", type_name=type_name, task_name=None)])])]),
                    "Jump")

    def test_the_travelling_row_is_still_taken(self):
        for text in ["Set Destination", "Jump"]:
            with self.subTest(label=text):
                self.assertTrue(
                    self.offers_a_step([tracker([capture_entry(
                        [travel_button(text, task_name=None)])])]),
                    "the travelling row stopped being a step")

    def test_a_hidden_entering_row_is_not_offered(self):
        """The issue's own negative case.

        The chain hides the tasks that are not available rather than removing
        them, so a hidden `Warp to Site` is the client saying the ship cannot
        take it yet. `_display` False **with** a region, so the region walk is
        not what drops it.
        """
        self.assertEqual(
            self.travel_label([tracker([capture_entry(
                [enter_button(displayed=False)])])]),
            "<none>")
        self.assertFalse(self.offers_a_step(
            [tracker([capture_entry([enter_button(displayed=False)])])]))

    def test_the_entering_row_is_admitted_by_name_and_not_by_its_type(self):
        """What the selector excludes, asked where it would be easiest to widen.

        A rule keyed on `TravelStateButtonTaskWidget` -- or on
        `endsWith "ButtonTaskWidget"`, which the mission runner uses and which
        would have matched the warp button -- admits every sibling the chain
        grows next. The same widget type under a task name nobody has read is
        declined.
        """
        self.assertEqual(
            self.travel_label([tracker([capture_entry([travel_button(
                ENTER_LABEL, type_name=ENTER_WIDGET_TYPE,
                task_name="objective_task_call_for_backup")])])]),
            "<none>")

    def test_a_conversation_button_beside_it_is_not_a_travel_step(self):
        """The sibling the mission runner's wider rule exists for.

        Its panel has a conversation button to press at hand-in, and
        `endsWith "ButtonTaskWidget"` is what reaches it there. Nothing says
        this chain will not grow one, and this is the case that says it would
        not be taken as a trip.
        """
        children = [tracker([capture_entry([
            travel_button("Start Conversation", type_name="ButtonTaskWidget",
                          task_name="objective_task_talk_to_agent"),
        ])])]
        self.assertEqual(self.travel_label(children), "<none>")
        self.assertFalse(self.offers_a_step(children))

    def test_the_entering_row_wins_nothing_the_allow_list_refuses(self):
        """Widening the parser must not widen `travelLabelIsACommand` by a word.

        Asked over the state labels only. **`Undock` is deliberately not among
        them**, and that is a correction rather than an omission: #280 lists it
        under "Not this" as a state read while the ship was undocking, and PR
        #282 read it off the live client as what this widget renders while the
        ship is **docked in the escalation's own system** -- a command, and the
        one that gets the ship out of a station it parked in. Whether a label is
        a command is `Bot.elm`'s answer and #282 is changing it; a case here
        asserting the old answer would go red on a change that is right.
        """
        for text in STATE_LABELS:
            with self.subTest(label=text):
                self.assertEqual(
                    self.travel_label(
                        [tracker([capture_entry([enter_button(text)])])]),
                    text,
                    "the parser stopped reading the label at all")
                self.assertFalse(
                    self.offers_a_step(
                        [tracker([capture_entry([enter_button(text)])])]),
                    "the branch acted on %r off the entering row" % text)

    def test_the_escalations_name_is_still_read_from_the_captures_shape(self):
        """The deeper nesting must not lose the site name the log line uses."""
        self.assertEqual(
            TheParserReadsTheTrackersOwnButton.site_names(
                self, [tracker([capture_entry([enter_button()])])]),
            SITE_NAME)

    def test_the_entrys_own_title_is_not_what_picks_the_task(self):
        """The capture's title reads `Travel to Location` beside a warp button.

        So a rule that had gone by the objective's title would have taken the
        wrong row, or none: the title is not a reliable guide to which button
        the chain is showing, and nothing here reads it.
        """
        self.assertEqual(
            self.travel_label([tracker([capture_entry(
                [enter_button()], title="Travel to Location")])]),
            ENTER_LABEL)


class BothRowsDisplayedAtOnce(unittest.TestCase):
    """Two **buttons** displayed at once: still the shape nobody has read, and
    pinned as what the parser does rather than as what it should do.

    Every capture of this chain shows one task *row* displayed and the other
    hidden. If both were ever shown, `OpportunityInfoPanelEntry.travelButton` is
    one button and the parser takes whichever the client lists first -- so
    `opportunityStepArrivingFirst`, which prefers an arriving label over a
    travelling one **between** entries, never sees the second button and cannot
    apply within one.

    Carrying both would need the field to become a list and the decision that
    reads it to fold over it, which is a change in `Bot.elm`. It is deliberately
    not made here: this PR is scoped to the parser, and the shape it would serve
    is unobserved. These cases exist so that the behaviour is recorded and a
    later change is one somebody argues for.

    **#291 is the ambiguity that did arrive, and it is not this one.** This
    class was written as the guard for "two candidates displayed at once" and
    anticipated the wrong pair: run 48 read a button beside the row's own
    **progress bar**, which nothing can press, sharing the button's `_name` and
    listed ahead of it. A guard that anticipates the wrong ambiguity reads as
    cover for the one that happens, so `TheProgressBarSharesTheButtonsName` is
    the case for the observed shape and this one keeps only the unobserved one.
    Nothing here changed with that fix -- both fixtures are buttons, so the
    preference cannot separate them and the client's order still decides -- and
    that unchangedness is asserted next door as well as here.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def entry_field(self, children, field):
        return TheParserReadsTheTrackersOwnButton.entry_field(
            self, children, field)

    def travel_label(self, children):
        return TheParserReadsTheTrackersOwnButton.travel_label(self, children)

    def both_displayed(self, order):
        buttons = {"travel": travel_button("Jump"),
                   "enter": enter_button(ENTER_LABEL)}
        return [tracker([capture_entry([buttons[which] for which in order])])]

    def test_exactly_one_button_is_surfaced_and_it_is_one_of_the_two(self):
        for order in [("travel", "enter"), ("enter", "travel")]:
            with self.subTest(order=order):
                self.assertIn(self.travel_label(self.both_displayed(order)),
                              ["Jump", ENTER_LABEL])

    def test_it_is_the_one_the_client_lists_first(self):
        """Which is the whole of the limitation, stated as the behaviour.

        Not an endorsement: with both rows live this takes the travelling step
        wherever the client draws it first, and the arrival preference #256
        built is not consulted. The tell on a flown run is the tracker offering
        `Jump` on a reading whose site the ship is already in.
        """
        self.assertEqual(self.travel_label(
            self.both_displayed(("travel", "enter"))), "Jump")
        self.assertEqual(self.travel_label(
            self.both_displayed(("enter", "travel"))), ENTER_LABEL)

    def test_one_displayed_beside_one_hidden_is_unambiguous(self):
        """Which is the shape the client has actually been read drawing."""
        children = [tracker([capture_entry([
            travel_button("Jump", displayed=False),
            enter_button(ENTER_LABEL),
        ])])]
        self.assertEqual(self.travel_label(children), ENTER_LABEL)
        children = [tracker([capture_entry([
            travel_button("Jump"),
            enter_button(ENTER_LABEL, displayed=False),
        ])])]
        self.assertEqual(self.travel_label(children), "Jump")


class TheProgressBarSharesTheButtonsName(unittest.TestCase):
    """#291, in the shape run 48 read it: the bar is admitted and sorts first.

    The two nodes the client drew, in the panel's own order:

        ProgressBarTaskWidget             _name=objective_task_travel_to_location  _display=None  '8 jumps | 0.6 Andabiar'
        TravelToLocationButtonTaskWidget  _name=objective_task_travel_to_location  _display=None  'Set Destination'

    `uiNodeIsOpportunityTravelTask` admits a node by type prefix **or** by the
    client's own `_name` for the objective task, and the bar carries that name,
    so the name half admits it. Neither node carries `_display`, so the display
    filter -- which is the selection everywhere else in this file -- separates
    nothing here. The bar is listed first, `travelButton.label` was
    `8 jumps | 0.6 Andabiar`, and the branch could not press a button plainly
    on screen.

    **The failure was silent, which is why the cases below ask two questions of
    one reading.** `escalationIsBeingWorked` asks only whether the label is
    readable text; `8 jumps` is, so the bot stood down for the escalation --
    correctly, by that rule -- while `travelLabelIsACommand` refused the same
    label and `opportunityTravelStep` answered `Nothing`. Run 48 stood down 234
    times and pressed the button zero times across three hours with nothing in
    the log saying a button had been missed. The two clauses **agreeing** is
    what the fix restores, and it is asserted rather than left implied.

    Every fixture here is the capture's own nesting and goes through the real
    `EveOnline.ParseUserInterface`, so the bar is admitted because that selector
    admits it rather than because a record was written by hand.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def entry_field(self, children, field):
        return TheParserReadsTheTrackersOwnButton.entry_field(
            self, children, field)

    def travel_label(self, children):
        return TheParserReadsTheTrackersOwnButton.travel_label(self, children)

    def offers_a_step(self, children):
        return TheBranchActsOnWhatTheTrackerOffers.offers_a_step(self, children)

    def reads_as_being_worked(self, children):
        return self.repl.evaluate([
            "reading |> Maybe.map escalationIsBeingWorked"
            " |> Maybe.withDefault False"],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    @staticmethod
    def the_capture(order=("bar", "button"), label="Set Destination"):
        """Run 48's two nodes, in whichever order a case wants to ask about."""
        nodes = {"bar": progress_bar(), "button": travel_button(label)}
        return [tracker([capture_entry([nodes[which] for which in order])])]

    def test_the_button_is_taken_beside_the_bar_that_sorts_first(self):
        """The reading run 48 took, and the label it produced was the bar's."""
        self.assertEqual(self.travel_label(self.the_capture()), "Set Destination")

    def test_the_branch_takes_it(self):
        """`opportunityTravelStep` answered `Nothing` on this reading."""
        self.assertTrue(
            self.offers_a_step(self.the_capture()),
            "the tracker drew 'Set Destination' beside a progress bar and the"
            " branch declined it")

    def test_the_stand_down_and_the_step_agree_on_this_reading(self):
        """The silence, asked as the two clauses answering the same question.

        A reading the bot stands down for and cannot take a step on is run 48:
        the escalation is being worked and nothing is being done about it. That
        `escalationIsBeingWorked` accepts any readable label is its own rule and
        is deliberately untouched here -- what this asserts is that the label it
        is now given is one `travelLabelIsACommand` accepts too.
        """
        children = self.the_capture()
        self.assertTrue(self.reads_as_being_worked(children),
                        "the escalation stopped reading as one being worked")
        self.assertTrue(self.offers_a_step(children),
                        "stood down for an escalation with no step to take")

    def test_the_bars_own_label_is_never_what_is_offered(self):
        """Whatever the client writes on the bar, and wherever it is listed."""
        for order in [("bar", "button"), ("button", "bar")]:
            for label in ["8 jumps | 0.6 Andabiar", "0.6 Andabiar", "3 jumps"]:
                with self.subTest(order=order, bar=label):
                    nodes = {"bar": progress_bar(label),
                             "button": travel_button("Set Destination")}
                    children = [tracker([capture_entry(
                        [nodes[which] for which in order])])]
                    self.assertEqual(self.travel_label(children),
                                     "Set Destination")

    def test_the_entering_rows_button_is_taken_beside_a_bar_too(self):
        """The same shape with the widget #280 was filed about.

        `TravelStateButtonTaskWidget` does not end with `ButtonTaskWidget`'s
        family in the same way the travelling row does, so a rule keyed on the
        wrong part of the type name would separate one of these pairs and not
        the other.
        """
        for order in [("bar", "button"), ("button", "bar")]:
            with self.subTest(order=order):
                nodes = {"bar": progress_bar(), "button": enter_button()}
                children = [tracker([capture_entry(
                    [nodes[which] for which in order])])]
                self.assertEqual(self.travel_label(children), ENTER_LABEL)
                self.assertTrue(self.offers_a_step(children))

    def test_both_spellings_of_the_travelling_row_win_over_the_bar(self):
        """`TravelToLocationButtonTask` is the spelling a suffix test loses."""
        for type_name in TRAVEL_WIDGET_TYPES:
            with self.subTest(type_name=type_name):
                children = [tracker([capture_entry([
                    progress_bar(),
                    travel_button("Jump", type_name=type_name),
                ])])]
                self.assertEqual(self.travel_label(children), "Jump")

    def test_a_bar_on_its_own_is_still_what_the_fallback_takes(self):
        """`List.head` is kept for the no-button case rather than replaced.

        A reading whose only admitted candidate is the bar has no button to
        prefer, so the entry offers the bar exactly as it did before -- and the
        label rule declines it, which is where a reading with no command has
        always ended. Asserting it is what makes the change a *preference*
        rather than a second filter: nothing that used to be offered stopped
        being offered.
        """
        children = [tracker([capture_entry([progress_bar()])])]
        self.assertEqual(self.travel_label(children), BAR_JUMPS)
        self.assertFalse(self.offers_a_step(children))

    def test_a_hidden_button_beside_a_shown_bar_is_still_not_taken(self):
        """The display filter is untouched and still outranks the preference.

        The chain hides the tasks that are not available, so a hidden button is
        the client saying the ship cannot take it -- and preferring a button
        must not reach past that. `_display` False **with** a region, so the
        region walk is not what drops it.
        """
        children = [tracker([capture_entry([
            progress_bar(),
            travel_button("Set Destination", displayed=False),
        ])])]
        self.assertEqual(self.travel_label(children), BAR_JUMPS)
        self.assertFalse(self.offers_a_step(children))

    def test_a_reading_that_yielded_a_button_yields_the_same_one(self):
        """The property the fix is claimed on, over every single-button shape.

        A preference among candidates can only change a reading whose chosen
        candidate was not a button, so every reading in this file that already
        produced one has to produce **the same** one. These are the fixtures the
        other classes assert on, gathered here so the claim is one case rather
        than an inference across five.
        """
        unchanged = [
            ("the capture's travelling row",
             [tracker([capture_entry([travel_button("Set Destination")])])],
             "Set Destination"),
            ("the capture's entering row",
             [tracker([capture_entry([enter_button()])])], ENTER_LABEL),
            ("the flattened entry",
             [tracker([expanded_entry([travel_button("Jump")])])], "Jump"),
            ("the second spelling",
             [tracker([capture_entry([travel_button(
                 "Jump", type_name=TRAVEL_WIDGET_TYPES[1],
                 task_name=None)])])], "Jump"),
            ("a button the client did not name",
             [tracker([expanded_entry([travel_button(
                 "Jump", named_label=False)])])], "Jump"),
            ("a displayed button beside a hidden one",
             [tracker([expanded_entry([
                 travel_button("Set Destination", displayed=False),
                 travel_button("Jump")])])], "Jump"),
            ("two buttons, the client's order",
             [tracker([capture_entry([
                 travel_button("Jump"), enter_button()])])], "Jump"),
            ("two buttons, the other order",
             [tracker([capture_entry([
                 enter_button(), travel_button("Jump")])])], ENTER_LABEL),
        ]
        for name, children, expected in unchanged:
            with self.subTest(reading=name):
                self.assertEqual(self.travel_label(children), expected)


class TheSelectorIsReadOutOfTheParser(unittest.TestCase):
    """The boundary, where an absence is not an expression."""

    @classmethod
    def setUpClass(cls):
        cls.parser = source_of(SAXRAT_PARSER_ELM)

    def test_the_prefix_still_covers_both_spellings_of_the_travelling_row(self):
        prefix = collapsed(
            body_of(self.parser, "opportunityTravelTaskTypePrefix"))
        self.assertIn('"TravelToLocationButtonTask"', prefix)
        for type_name in TRAVEL_WIDGET_TYPES:
            self.assertTrue(type_name.startswith("TravelToLocationButtonTask"),
                            type_name)

    def test_the_named_tasks_are_the_clients_two_and_no_more(self):
        listed = collapsed(body_of(self.parser, "opportunityTravelTaskNames"))
        for name in (TRAVEL_TASK_NAME, ENTER_TASK_NAME):
            self.assertIn('"%s"' % name, listed)
        self.assertEqual(len(re.findall(r'"', listed)), 4,
                         "the task-name list has grown or shrunk: %s" % listed)

    def test_the_parse_does_not_widen_to_the_whole_widget_family(self):
        """`endsWith "ButtonTaskWidget"` is the mission runner's, not this one.

        It would have matched the warp button, which is why the issue names it;
        it also admits every sibling in `buttons_container` sight-unseen.
        """
        self.assertNotIn('String.endsWith "ButtonTaskWidget"',
                         collapsed(self.parser))

    def test_nothing_here_matches_the_state_widget_by_type(self):
        """So the entering row is admitted by the client's name for its task."""
        self.assertNotIn('"%s"' % ENTER_WIDGET_TYPE, self.parser)

    def test_the_button_preference_is_the_substring_both_buttons_carry(self):
        """#291's separator, checked against the three type names it sorts.

        A suffix would have been the obvious spelling and is wrong for the same
        reason the selector above is a prefix: `TravelToLocationButtonTask`,
        the later of the two spellings, does not end with `ButtonTaskWidget`.
        """
        infix = collapsed(body_of(
            self.parser, "opportunityTravelTaskButtonTypeInfix"))
        self.assertIn('"ButtonTask"', infix)
        for type_name in tuple(TRAVEL_WIDGET_TYPES) + (ENTER_WIDGET_TYPE,):
            self.assertIn("ButtonTask", type_name,
                          "%s stopped reading as pressable" % type_name)
        self.assertNotIn("ButtonTask", BAR_WIDGET_TYPE)
        rule = collapsed(body_of(
            self.parser, "uiNodeIsOpportunityTravelTaskButton"))
        self.assertIn("String.contains opportunityTravelTaskButtonTypeInfix",
                      rule)

    def test_the_preference_reorders_what_the_selector_already_admitted(self):
        """It is a preference and not a second filter, read out of the parse.

        The candidates are still whatever `uiNodeIsOpportunityTravelTask` and
        the display filter agree on; the button rule is applied to that list,
        and `List.head` over the same list is what answers where no candidate
        is a button. A version that filtered the candidates down to buttons
        would make a bar-only reading offer nothing, which is a narrowing --
        `test_a_bar_on_its_own_is_still_what_the_fallback_takes` is that half.
        """
        candidates = let_binding_by_indentation(
            self.parser, "parseOpportunityInfoPanelEntry",
            "displayedTravelTaskNodes")
        self.assertIn("uiNodeIsOpportunityTravelTask", candidates)
        self.assertIn("nodeIsDisplayedFromDictEntries", candidates)
        self.assertNotIn("uiNodeIsOpportunityTravelTaskButton", candidates)

        chosen = let_binding_by_indentation(
            self.parser, "parseOpportunityInfoPanelEntry", "travelButtonNode")
        self.assertIn("uiNodeIsOpportunityTravelTaskButton", chosen)
        self.assertIn("displayedTravelTaskNodes |> List.head", chosen)


class TheVendoredParserPolicyIsUnbroken(unittest.TestCase):
    """What "all six, identically" actually requires, checked rather than read.

    CLAUDE.md states the policy over the whole file; what the repo *enforces* is
    `test_game_log_channel.VendoredParserTest`, which compares the game-log
    block byte for byte across the six copies and pins the type name the host
    and the parser have to agree on. The copies already diverge outside that
    block -- saxrat carries target hitpoints and two manoeuvre types the combat
    bot does not, and `parseAgentMissionInfoPanelEntry` exists in the mission
    runner alone -- so panel parsing for one app's panel is an app-local
    addition of exactly the shape already there, and this change lands in
    saxrat's copy only.
    """

    APPS_DIR = os.path.dirname(SAXRAT_DIR)

    def parser_paths(self):
        paths = []
        for app in sorted(os.listdir(self.APPS_DIR)):
            path = os.path.join(self.APPS_DIR, app, "EveOnline",
                                "ParseUserInterface.elm")
            if os.path.isfile(path):
                paths.append(path)
        self.assertEqual(len(paths), 6, paths)
        return paths

    def test_only_saxrats_copy_gained_the_tracker(self):
        for path in self.parser_paths():
            source = source_of(path)
            expected = path.startswith(SAXRAT_DIR + os.sep)
            self.assertEqual(
                "parseOpportunityInfoPanelEntriesFromUITreeRoot" in source,
                expected, path)

    def test_the_copies_already_diverged_before_this(self):
        """So the enforced policy is the block, not the file.

        Asserted rather than argued: the mission runner's own mission-tracker
        parse is in one copy of six, and it predates this change.
        """
        carrying = [path for path in self.parser_paths()
                    if "parseAgentMissionInfoPanelEntry" in source_of(path)]
        self.assertEqual(len(carrying), 1, carrying)

    def test_every_copy_still_carries_the_block_the_policy_covers(self):
        for path in self.parser_paths():
            self.assertIn(
                "    , gameLogEntriesSinceLastReading = "
                "parseGameLogEntriesSinceLastReadingFromUITreeRoot uiTree\n",
                source_of(path), path)


class TheRecordedSaxratRunsTest(unittest.TestCase):
    """What runs 25 and 26 say, as relations rather than as the issue's counts.

    A growing corpus must not turn a true claim red, so nothing here asserts
    "44" or "168"; what it asserts is that those runs travelled by stargate
    repeatedly and reached the tracker not once.
    """

    def test_the_tracker_was_never_used_while_the_bot_jumped_gates(self):
        asked = False
        for path in saxrat_runs(25, 26):
            name = os.path.basename(path)
            lines = read_log(path).splitlines()
            jumps = sum(1 for line in lines if STARGATE_JUMP_LINE in line)
            tracker_uses = sum(1 for line in lines
                               if OLD_OPPORTUNITY_LINE in line)
            self.assertTrue(
                jumps > 10,
                "%s: only %d stargate jumps -- this is no longer the run the "
                "issue was measured on" % (name, jumps))
            self.assertEqual(
                tracker_uses, 0,
                "%s: the tracker was used %d times, so the defect this change "
                "removes is no longer recorded here" % (name, tracker_uses))
            asked = True
        self.assertTrue(asked, "no recorded run to consult")

    def test_the_tracker_has_only_ever_offered_a_travelling_label_here(self):
        """#280's shape, as much of it as this machine's corpus can carry.

        The run the issue quotes -- `saxrat_20260816-173606` -- is not here; the
        project also flies on two Windows hosts with their own logs. What is
        here is every saxrat run that has taken a tracker step since #252 made
        the step readable at all, and across all of them the tracker's own
        decision line names **only** the travelling row's labels. Not one
        arriving label, on any reading, in any run.

        Asserted as that relation rather than as a count, and it is exactly what
        `opportunityStepArrivingFirst` (#256) and the arrival-outranks-the-gate
        ordering (#261) have had to work with: neither has ever had an arriving
        label to prefer.
        """
        offered = []
        for path in every_saxrat_run():
            offered.extend(tracker_offers(path))
        self.assertTrue(
            offered,
            "no recorded run ever took a tracker step, so this corpus cannot "
            "say what the tracker has offered")
        arriving = sorted({label for label in offered
                           if label.strip().lower()
                           in {"warp to site", "warp to location", "dock"}})
        # Until run 49 this asserted `arriving == []`, and that was true of
        # every run this machine had: the tracker's button was unreachable
        # (#291), so no bot had ever pressed one and no corpus could hold an
        # arriving label. Run 49 pressed `Set Destination`, nine `Jump`s and
        # then `Warp to Site`, entered eight sites and looted six commanders --
        # so the premise `opportunityStepArrivingFirst` (#256) and the
        # arrival-outranks-the-gate ordering (#261) were both built without is
        # finally in the recordings.
        #
        # Kept as a case rather than deleted, inverted: what it now refuses is
        # the corpus going *back* to holding no arriving label, which would mean
        # the button had become unreachable again.
        self.assertIn(
            "Warp to Site", arriving,
            "no recorded run offers an arriving label any more -- #291's fix "
            "has regressed and the tracker's button is unreachable again")
        # The whole vocabulary the tracker has ever been *seen* offering here.
        # `Warp to Location` and `Dock` are in `COMMAND_LABELS` on the mission
        # runner's evidence rather than this bot's, and neither has been read
        # off an escalation -- so a label outside this set is the client saying
        # something nobody has designed for, which is worth a red case whichever
        # label it is.
        self.assertTrue(
            set(offered) <= {"Jump", "Set Destination", "Warp to Site"},
            "the tracker offered something new: %s" % sorted(set(offered)))

    def test_the_old_search_never_matched_the_other_labels(self):
        """Which is the defect: three of four labels were invisible to it.

        The recorded runs carry the whole-tree search's own decision line and no
        other, so a run that travelled by gate never once found `Jump` or
        `Set Destination` through it.
        """
        for path in saxrat_runs(25, 26):
            lines = read_log(path).splitlines()
            self.assertEqual(
                [line for line in lines if "Warp to Site" in line], [],
                "%s: the old search's literal appears after all"
                % os.path.basename(path))


if __name__ == "__main__":
    unittest.main()

class TheEscalationDestinationIsReadAndBoundedTest(unittest.TestCase):
    """An escalation may not send this bot below the empire line.

    The client writes the trip's destination on the objective chain's progress
    bar -- `8 jumps`, `0.6 Andabiar` -- and until #291 that row was the thing
    being mistaken for the travel button. Now that a button is preferred over
    it, the bar is read for what it does carry, and the security status is
    finally in the bot's hands.

    **Paid for once.** An escalation fourteen jumps into `0.3 Arodan` sat in the
    queue from the first minute of a session; the bot took it, and the ship was
    killed there by a pilot with 19,739 kills flying a Succubus. Warp scrambled,
    so the retreat could not have worked either -- the only defence available
    against a player is not to be there.

    **Both readers are gated, and that is the load-bearing half.** Refusing the
    destination in `opportunityTravelStep` alone would leave
    `escalationIsBeingWorked` true, and the stand-down would then hold every dry
    grid for forty readings waiting for a step the bot had already decided never
    to take -- which is #291's own defect rebuilt from the other side.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(
            TrackerRepl,
            preamble=list(PREAMBLE) + ["import EveOnline.ParseUserInterface as P"])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def destination(self, cells):
        listing = "[" + ", ".join('"%s"' % c for c in cells) + "]"
        return self.repl.strings(
            ["Debug.toString (P.parseOpportunityDestination %s)" % listing])[0]

    def test_the_security_and_system_are_read(self):
        self.assertIn("security = Just 0.6", self.destination(["8 jumps", "0.6 Andabiar"]))
        self.assertIn('systemName = Just "Andabiar"', self.destination(["8 jumps", "0.6 Andabiar"]))

    def test_the_jumps_cell_is_not_read_as_the_security(self):
        """`8 jumps` is the same shape as `0.6 Andabiar` and is listed first.

        The first version of this answered `security = Just 8` for a system
        called `jumps`, and only running it said so -- the types are identical.
        """
        said = self.destination(["8 jumps", "0.6 Andabiar"])
        self.assertNotIn("security = Just 8", said)
        self.assertNotIn('systemName = Just "jumps"', said)

    def test_the_order_of_the_cells_does_not_decide(self):
        forwards = self.destination(["14 jumps", "0.3 Arodan"])
        backwards = self.destination(["0.3 Arodan", "14 jumps"])
        self.assertEqual(forwards, backwards)
        self.assertIn("security = Just 0.3", forwards)

    def test_a_negative_security_is_read_rather_than_refused(self):
        """Nullsec is a real answer and must reach the rule as one."""
        self.assertIn("security = Just -1",
                      self.destination(["9 jumps", "-1.0 J155416"]))

    def test_a_cell_that_does_not_parse_yields_nothing_not_a_default(self):
        """A fabricated `0.0` would read as nullsec -- the worst answer there is."""
        said = self.destination(["Set Destination"])
        self.assertIn("security = Nothing", said)
        self.assertNotIn("security = Just 0", said)

    def test_the_threshold_is_the_empire_line(self):
        self.assertEqual(
            self.repl.strings(["Debug.toString Bot.defaultEscalationMinimumSecurity"])[0],
            "0.5",
            "the default is no longer 0.5, which is where CONCORD stops "
            "answering rather than a number somebody tuned")

    def permits(self, minimum, security):
        return self.repl.evaluate(
            ["Bot.securityIsPermitted %s %s" % (minimum, security)])[0]

    def test_an_unreadable_security_refuses_the_trip(self):
        """The one place in this file where absent must read as dangerous.

        Declining an escalation costs ISK; accepting one that turns out to be
        lowsec costs the hull, the loot and the implants. Executed rather than
        read, because a substring test over the branch passes for any body that
        merely mentions the words.
        """
        self.assertFalse(self.permits("0.5", "Nothing"))

    def test_the_line_is_at_the_threshold_and_both_sides_of_it(self):
        self.assertTrue(self.permits("0.5", "(Just 0.5)"))
        self.assertTrue(self.permits("0.5", "(Just 0.6)"))
        self.assertFalse(self.permits("0.5", "(Just 0.4)"))
        self.assertFalse(self.permits("0.5", "(Just 0.3)"))
        self.assertFalse(self.permits("0.5", "(Just -1.0)"))

    def test_an_operator_can_lower_it_but_has_to_say_so(self):
        """`escalation-minimum-security=0` allows anything, deliberately."""
        self.assertTrue(self.permits("0", "(Just 0.3)"))
        self.assertTrue(self.permits("0", "(Just 0.0)"))
        self.assertFalse(self.permits("0", "Nothing"),
                         "an unreadable security is still refused however low "
                         "the threshold is set")

    def test_every_site_that_acts_on_an_escalation_narrows_first(self):
        """The permission is applied where the bot acts, not inside the readers.

        `opportunityTravelStep`, `warpToOpportunitySiteIfAvailable` and
        `escalationIsBeingWorked` keep their single-argument signatures -- some
        ninety-five cases in this file ask them what the tracker is offering,
        and that is a question about the panel rather than about settings. So
        the *reading* is narrowed at each site that decides on one, and this is
        what stops a fifth site being added without it.

        The stand-down reader matters as much as the travel one. Gating only the
        travel step would leave `escalationIsBeingWorked` true for a lowsec
        escalation, and the bot would hold every dry grid for forty readings
        waiting for a step it had already refused -- #291's defect rebuilt from
        the other side.
        """
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        acting = re.findall(
            r"(?:warpToOpportunitySiteIfAvailable|escalationIsBeingWorked|"
            r"opportunityTravelStep)\s*\(?\s*(escalationEntriesPermitted|"
            r"context\.readingFromGameClient|readingFromGameClient)",
            source)
        bare = [a for a in acting if a != "escalationEntriesPermitted"]
        narrowed = [a for a in acting if a == "escalationEntriesPermitted"]
        self.assertGreaterEqual(
            len(narrowed), 4,
            "fewer call sites narrow the reading than this change wired: %r" % acting)
        self.assertEqual(
            [b for b in bare if b.startswith("context.")], [],
            "a decision site passes the whole reading to an escalation reader "
            "without narrowing it first, so a lowsec escalation reaches it")

    def test_the_narrowing_is_what_applies_the_permission(self):
        """One expression serves both readers, so they cannot drift apart."""
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        body = source[source.index("escalationEntriesPermitted botSettings readingFromGameClient ="):][:400]
        self.assertIn("escalationDestinationIsPermitted", body)
        self.assertIn("List.filter", body)
