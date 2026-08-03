"""Tests for reading a travel step out of an objective-chain mission panel.

Run 14 sat docked for its last 750 readings on
`Technological Secrets (3 of 3) -- 3 jumps`, printing

    + I see no ship UI, assume we are docked.
    ++ A mission is running but the tracker offers no travel step from here.

while the client rendered a perfectly good `Set Destination` button in the
mission tracker. Read live off the stuck client, the panel held

    AgentMissionInfoPanelEntry        _name=agent_missions:3008916
      ObjectiveChainEntry             _name=objective_chain_52
        ObjectiveEntry                _name=objective_travel_to_agent
          ContainerAutoSize           _name=buttons_container
            TravelToLocationButtonTaskWidget  _name=objective_task_travel_to_agent
              EveLabelMedium          _name=label   Set Destination
            ButtonTaskWidget          _name=objective_task_talk_to_agent
              EveLabelMedium          _name=label   Start Conversation

and `parseAgentMissionInfoPanelEntry` was looking for a node whose `_name`
starts with `missionObjective_button_location` -- a name that appears **nowhere
in this layout**. So `locationButton` was `Nothing`, `missionTravelStep` was
`Nothing`, and the bot correctly reported that it had no travel step while the
step sat on screen. The mission was tracked (the panel entry is present, and the
info panel carried its four `ButtonIconInfoPanel` toggles), so none of the
existing "a mission must be tracked" advice applies.

**Two layouts, and the difference is per objective type.** The five missions run
14 completed before this one all rendered the single button this parser was
written against, whose label changes as the mission advances (`Undock`,
`Warp to Location`, `Dock`, `Start Conversation`). An objective chain instead
gives every task its own widget and shows only the live one. Matching the
*type* name rather than `_name` is what makes the new rule general: `_name`
carries the objective (`objective_task_travel_to_agent`,
`objective_task_talk_to_agent`) and would need a fresh literal per objective
type, while the type name says what the widget is.

**The suffix match covers both widgets deliberately.** The single button also
becomes `Start Conversation` at hand-in, so a rule that took only
`TravelToLocationButtonTaskWidget` would fly the ship across the grid and then
strand it at the agent with nothing to press.

**What is verified here and what is not.** The travel leg is checked against the
exact node shapes read off the stuck client, driven through the *real* parser in
`elm repl` rather than restated in Python. The hand-in leg is not: on the stuck
client the `Start Conversation` widget carries `_display` False and **no display
region at all**, so `listDescendantsWithDisplayRegion` drops it before any rule
here sees it. That it gains a region when it becomes the live task is inferred
from the travel widget having one, not observed -- and it is the thing to watch
on the first run that reaches an agent this way.

That asymmetry is also why the display filter stays in the selection rather than
being left to `missionTravelStep`. Here the hidden widget has no region and is
already gone; a client that rendered it hidden-but-placed would otherwise have
the parser hand back a button the bot then discards, which is the same stall
reached by a longer road.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
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
PARSER_ELM = os.path.join(MISSION_RUNNER_DIR, "EveOnline", "ParseUserInterface.elm")

# The type name the client gives the travel task widget, and the suffix shared
# by it and the conversation widget beside it. Both read off the live client.
TRAVEL_WIDGET_TYPE = "TravelToLocationButtonTaskWidget"
CONVERSATION_WIDGET_TYPE = "ButtonTaskWidget"
WIDGET_TYPE_SUFFIX = "ButtonTaskWidget"

_address = iter(range(100000, 999999))


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


def label_node(text):
    return node("EveLabelMedium", {"_name": "label", "_setText": text},
                region=(0, 0, 100, 16))


def task_widget(type_name, name, text, displayed=True, with_region=True):
    entries = {"_name": name}
    if not displayed:
        entries["_display"] = False
    return node(type_name, entries, [label_node(text)],
                region=(0, 4, 240, 24) if with_region else None)


def panel_entry(children):
    """An `AgentMissionInfoPanelEntry` as the client renders it."""
    return node("AgentMissionInfoPanelEntry", {"_name": "agent_missions:3008916"},
                children, region=(0, 0, 300, 200))


def tree_with(entry):
    return node("UIRoot", {}, [entry], region=(0, 0, 1920, 1080))


def objective_chain_entry(widgets):
    """The layout that stalled run 14: chain -> objective -> per-task widgets."""
    return panel_entry([
        node("ObjectiveChainEntry", {"_name": "objective_chain_52"}, [
            node("ObjectiveEntry", {"_name": "objective_travel_to_agent"}, [
                node("ContainerAutoSize", {"_name": "buttons_container"},
                     widgets, region=(0, 0, 240, 60)),
            ], region=(0, 0, 240, 80)),
        ], region=(0, 0, 240, 100)),
    ])


def single_button_entry(text):
    """The layout this parser was originally written against."""
    return panel_entry([
        node("ContainerAutoSize",
             {"_name": "missionObjective_button_location_1"},
             [label_node(text)], region=(0, 4, 240, 24)),
    ])


class ElmRepl:
    """The real parser, answering for itself.

    Unlike the other suites here this drives `EveOnline.ParseUserInterface`
    directly rather than `Bot`, so no source needs opening -- both that module
    and `EveOnline.MemoryReading` already expose everything.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-objective-chain-")
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

    def ask(self, expressions):
        script = ("import EveOnline.MemoryReading\n"
                  "import EveOnline.ParseUserInterface\n"
                  + "".join(e + "\n" for e in expressions))
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        answers = [a == "True" for a in re.findall(r"(True|False) : Bool", plain)]
        return answers, plain, result.stderr

    def evaluate(self, expressions):
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def travel_label_of(self, tree):
        """What the parser makes of this tree's travel step, as an assertion."""
        return (
            '(EveOnline.MemoryReading.decodeMemoryReadingFromString """%s"""'
            ' |> Result.toMaybe'
            ' |> Maybe.map EveOnline.ParseUserInterface.parseUITreeWithDisplayRegionFromUITree'
            ' |> Maybe.map EveOnline.ParseUserInterface.parseUserInterfaceFromUITree'
            ' |> Maybe.andThen (.agentMissionInfoPanelEntries >> List.head)'
            ' |> Maybe.andThen .locationButton'
            ' |> Maybe.andThen .label)'
        ) % json.dumps(tree)

    def works(self):
        answers, plain, stderr = self.ask([
            "%s == Just \"Set Destination\""
            % self.travel_label_of(tree_with(single_button_entry("Set Destination")))])
        return answers == [True], plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def elm_is_available():
    return shutil.which("elm") is not None


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheRealParserReadsBothLayouts(unittest.TestCase):

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

    def assert_travel_label(self, tree, expected):
        expression = "%s == %s" % (
            self.repl.travel_label_of(tree),
            'Just "%s"' % expected if expected is not None else "Nothing")
        self.assertEqual([True], self.repl.evaluate([expression]),
                         "expected travel label %r" % (expected,))

    def test_the_stalled_panel_now_yields_its_travel_step(self):
        """Run 14's exact shape, which used to parse as no travel step."""
        self.assert_travel_label(
            tree_with(objective_chain_entry([
                task_widget(TRAVEL_WIDGET_TYPE, "objective_task_travel_to_agent",
                            "Set Destination"),
                task_widget(CONVERSATION_WIDGET_TYPE, "objective_task_talk_to_agent",
                            "Start Conversation", displayed=False, with_region=False),
            ])),
            "Set Destination")

    def test_the_old_single_button_layout_is_unchanged(self):
        for label in ["Undock", "Warp to Location", "Dock", "Start Conversation"]:
            with self.subTest(label=label):
                self.assert_travel_label(
                    tree_with(single_button_entry(label)), label)

    def test_the_hand_in_step_is_read_once_the_client_shows_it(self):
        """The travel task done, the conversation task live."""
        self.assert_travel_label(
            tree_with(objective_chain_entry([
                task_widget(TRAVEL_WIDGET_TYPE, "objective_task_travel_to_agent",
                            "Set Destination", displayed=False, with_region=False),
                task_widget(CONVERSATION_WIDGET_TYPE, "objective_task_talk_to_agent",
                            "Start Conversation"),
            ])),
            "Start Conversation")

    def test_a_widget_hidden_but_still_placed_is_not_offered(self):
        """`_display` False with a region is the case the region filter misses."""
        self.assert_travel_label(
            tree_with(objective_chain_entry([
                task_widget(TRAVEL_WIDGET_TYPE, "objective_task_travel_to_agent",
                            "Set Destination", displayed=False, with_region=True),
            ])),
            None)

    def test_an_entry_offering_nothing_still_offers_nothing(self):
        """The panel with no task widget at all -- on grid, nothing to travel to."""
        self.assert_travel_label(tree_with(objective_chain_entry([])), None)

    def test_the_single_button_wins_where_both_are_present(self):
        """Order matters only if a client ever renders both; the old rule leads."""
        entry = single_button_entry("Dock")
        entry["children"].append(
            node("ContainerAutoSize", {"_name": "buttons_container"}, [
                task_widget(TRAVEL_WIDGET_TYPE, "objective_task_travel_to_agent",
                            "Set Destination"),
            ], region=(0, 40, 240, 60)))
        self.assert_travel_label(tree_with(entry), "Dock")


class TheRuleIsWrittenAgainstTypeNamesNotObjectiveNames(unittest.TestCase):
    """Read out of the source: the `_name` values are per objective type, so a
    rule resting on them needs a new literal for every objective the client
    invents. That is the drift this change exists to avoid."""

    def setUp(self):
        with open(PARSER_ELM, encoding="utf-8") as source:
            self.source = source.read()

    def test_it_matches_the_widget_type_suffix(self):
        self.assertIn('String.endsWith "%s"' % WIDGET_TYPE_SUFFIX, self.source)

    def test_it_does_not_match_the_objective_specific_names(self):
        for name in ["objective_task_travel_to_agent", "objective_task_talk_to_agent"]:
            self.assertNotIn('"%s"' % name, self.source.split("{-|")[0] + "".join(
                part.split("-}")[-1] for part in self.source.split("{-|")[1:]),
                "%s is matched as a literal outside the comments" % name)

    def test_the_old_rule_is_still_there(self):
        self.assertIn("missionObjective_button_location", self.source)

    def test_the_selection_filters_on_display(self):
        self.assertIn("nodeIsDisplayedFromDictEntries", self.source)

    def test_absent_display_still_means_shown(self):
        helper = re.search(
            r"nodeIsDisplayedFromDictEntries uiNode =.*?Maybe\.withDefault (\w+)",
            self.source, re.S)
        self.assertIsNotNone(helper)
        self.assertEqual("True", helper.group(1))


if __name__ == "__main__":
    unittest.main()
