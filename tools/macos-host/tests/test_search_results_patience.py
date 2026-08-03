"""The search-results branch, and the two things run 17 proved it was missing.

Run 17 was the first live execution of the home-station trip. The bay was empty,
the trip began, `searchQueryForStation` derived the typable tail correctly and
the search ran 25 times. Then a Search Results window appeared and

    +++ The search results do not offer 'Amarr VIII (Oris) - Emperor Family Academy'.
    ++++ I am stuck here and need help to continue.

repeated for **192 consecutive readings** -- the whole of the last 119 seconds of
the session. The wind-down never got past it, the ship never went home, and the
recording cannot say why, because that line names what was not found and never
what was.

Two properties are asserted here, and they are different properties.

**Absence is only evidence once the window is populated enough to be believed.**
The same rule `ammoSwapMenuEntriesBeforeTrusted` already applies to a module's
context menu: a design that reads absence as proof will believe a half-built
window. `searchResultsTextsBeforeTrusted` gates the *negative* conclusion only --
a window offering `Stations (` is acted on however few rows it has -- and the
cases below fail if that ordering is inverted, because a threshold in front of
the positive action would stall a search that matched nothing but stations.

**The patience is bounded, and the counter can reach the bound.** A wait nothing
ends is #34, #41 and #53, and a bound whose counter cannot advance is #34
exactly. So the counter's arithmetic is asserted branch by branch, the way
`test_ammo_silenced_bound` learned to.

The wording of the four diagnoses is executed rather than restated: they are
what makes the next failure of this branch diagnosable from a log, so a change
that collapses two of them into one has to fail here.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
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
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
CLAUDE_MD = os.path.join(REPO_DIR, "CLAUDE.md")

# The station this failed on, and the row form CLAUDE.md recorded off the live
# client -- security status in colour markup ahead of the name, jump count
# behind it. Both quoted rather than paraphrased: the full-name match is the
# step the bot performs on this exact text.
STATION_NAME = "Amarr VIII (Oris) - Emperor Family Academy"
RENDERED_ROW = ("<color=0xFF7BB2FF>0.9</color> Amarr VIII (Oris) - "
                "Emperor Family Academy (1 Jump)")

# The collapsed group header the branch clicks to expand. CLAUDE.md's step 3.
STATIONS_GROUP_LABEL = "Stations ("

# The line run 17 printed 192 times. Kept whole so a rewording that breaks a
# log grep an operator already has is visible here.
RUN_17_GIVE_UP = "The search results do not offer '"


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def squeezed(text):
    """Whitespace-insensitive, so elm-format may lay the source out as it likes."""
    return re.sub(r"\s+", " ", text)


def record_field_body(source, name):
    """The right-hand side of one field of the memory record being built.

    Fields sit at four spaces and start with a comma, so the terminator is the
    next such line or the closing brace.
    """
    start = source.index("\n    , " + name + " =\n")
    rest = source[start + len("\n    , " + name + " =\n"):]
    end = re.search(r"\n    (?:, \w+ =|\})", rest)
    return rest[:end.start()] if end else rest


def function_body(source, name):
    """A top-level definition, from its type annotation to the next one."""
    start = source.index("\n" + name + " :")
    rest = source[start + 1:]
    end = re.search(r"\n\n\n", rest)
    return rest[:end.start()] if end else rest


def branch_results(body):
    """What each branch of an `if`/`else if` chain evaluates to.

    Comments and blank lines dropped, then anything that is not part of a
    condition is a result -- `test_ammo_silenced_bound`'s reader, for the same
    reason: a counter written some other shape shows up as an unrecognised
    result and fails loudly rather than passing quietly.
    """
    results = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped == "else" or (
                stripped.startswith(("if ", "else if ")) and stripped.endswith(" then")):
            continue
        results.append(stripped)
    return results


def int_constant(source, name):
    match = re.search(r"^" + name + r" : Int\n" + name + r" =\n\s+(\d+)",
                      source, re.MULTILINE)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return int(match.group(1))


class ThePatienceIsBounded(unittest.TestCase):
    """The give-up is right eventually and wrong on the first reading."""

    def setUp(self):
        self.source = bot_elm()
        self.body = function_body(self.source, "routeToStationByName")

    def test_the_give_up_is_behind_the_bound(self):
        # The defect, stated as the thing that must be true. Deleting the guard
        # restores run 17 exactly.
        self.assertIn(
            squeezed("if searchResultsWithoutStationInfoTicksBeforeGivingUp "
                     "<= readingsSoFar then"),
            squeezed(self.body),
            "the results-window branch concludes without consulting the "
            "patience counter, which is run 17")

    def test_asking_for_help_is_reachable_only_after_the_bound(self):
        # Two give-ups live in this function: no search bar at all, and the
        # bounded one. A third would be an unbounded conclusion by another name.
        self.assertEqual(
            2, self.body.count("askForHelpToGetUnstuck"),
            "routeToStationByName has an unexpected number of give-ups")
        guard = self.body.index("searchResultsWithoutStationInfoTicksBeforeGivingUp <=")
        after_guard = self.body[guard:]
        self.assertIn(
            RUN_17_GIVE_UP, after_guard,
            "the 'do not offer' conclusion is drawn before the bound is checked")
        self.assertNotIn(
            RUN_17_GIVE_UP, self.body[:guard],
            "a copy of the conclusion survives ahead of the guard, so the "
            "branch can still reach it on the first reading")

    def test_the_states_short_of_the_bound_wait_rather_than_conclude(self):
        after_guard = self.body[
            self.body.index("searchResultsWithoutStationInfoTicksBeforeGivingUp <="):]
        self.assertIn(
            "waitForProgressInGame", after_guard,
            "nothing in the branch waits, so the counter can never advance "
            "through a reading the bot spends here")

    def test_the_bound_is_long_enough_for_a_working_sequence(self):
        # Window opens, group is expanded, the expansion settles, the row is
        # double-clicked, the info window arrives. A bound under that would
        # give up on searches that were about to work.
        bound = int_constant(
            self.source, "searchResultsWithoutStationInfoTicksBeforeGivingUp")
        self.assertGreaterEqual(bound, 10)
        self.assertLess(bound, 192, "run 17 sat here for 192 readings; a bound "
                                    "at or above that bounds nothing it saw")


class TheCounterCanReachItsBound(unittest.TestCase):
    """A bound whose counter cannot advance is indistinguishable from no bound."""

    COUNTER = "searchResultsWithoutStationInfoTicks"

    def setUp(self):
        self.body = record_field_body(bot_elm(), self.COUNTER)

    def test_every_branch_resets_holds_starts_or_increments(self):
        previous = "botMemoryBefore." + self.COUNTER
        allowed = {"0", "1", previous, previous + " + 1"}
        for result in branch_results(self.body):
            self.assertIn(
                result, allowed,
                self.COUNTER + " has a branch evaluating to " + repr(result) +
                " -- a counter may only reset, hold, start or increment")

    def test_it_has_a_branch_that_increments(self):
        self.assertIn(
            "botMemoryBefore." + self.COUNTER + " + 1",
            branch_results(self.body),
            "the counter never advances, so the bound is unreachable -- #34")

    def test_it_advances_in_exactly_the_state_run_17_was_in(self):
        # A results window up, no station info window: the increment is the
        # `else`, so that state is what advances it. This is the reachability
        # statement, and it is measured rather than argued -- run 17 held that
        # state for 192 consecutive readings.
        squeezed_body = squeezed(self.body)
        self.assertIn(
            "if not (searchResultsWindowIsOpen context.readingFromGameClient) then 0",
            squeezed_body)
        self.assertIn(
            "else if stationInfoWindowIsOpen context.readingFromGameClient then 0",
            squeezed_body)

    def test_it_is_not_reset_by_the_route_being_set(self):
        # The results window stays open through the "Set Destination" click and
        # the route panel catching up. Resetting on the route rather than on the
        # info window would charge those readings to this budget.
        self.assertNotIn("routeIsSet", self.body)


class TheThresholdGatesOnlyTheNegative(unittest.TestCase):
    """A half-built window is not believed; a thin one is still acted on."""

    def setUp(self):
        self.source = bot_elm()
        self.body = function_body(self.source, "routeToStationByName")

    def test_expanding_the_group_is_not_behind_the_threshold(self):
        # A search matching stations and nothing else renders the caption and
        # one group header. Making that wait for a row threshold it can never
        # reach would stall the working case.
        expand = self.body.index("Expand the Stations group")
        threshold = self.body.index("searchResultsTextsBeforeTrusted")
        self.assertLess(
            expand, threshold,
            "the trust threshold sits in front of the click that expands the "
            "group, so a stations-only result is made to wait for rows that "
            "only appear once the group is expanded")

    def test_the_threshold_is_above_an_empty_window_and_at_the_floor_of_a_real_one(self):
        trusted = int_constant(self.source, "searchResultsTextsBeforeTrusted")
        self.assertGreater(
            trusted, 1,
            "a window carrying only its caption would be believed")
        # CLAUDE.md's live capture: the caption and two collapsed group headers.
        self.assertLessEqual(
            trusted, 3,
            "above the only populated window this repo has ever recorded")

    def test_the_group_header_matches_what_the_client_writes(self):
        with open(CLAUDE_MD, encoding="utf-8") as handle:
            documented = handle.read()
        self.assertIn(
            STATIONS_GROUP_LABEL, self.body,
            "the branch no longer looks for the collapsed group header")
        self.assertIn(
            "Stations (26)", documented,
            "CLAUDE.md no longer records the header this literal is derived "
            "from -- re-derive it before trusting the match")

    def test_a_second_click_on_the_toggle_is_settled_for(self):
        # The header is a toggle: clicking it again before the client has
        # rendered the expansion closes the group. Without the settle the branch
        # flaps open and shut for as long as the bound allows.
        expand = self.body.index("Expand the Stations group")
        self.assertIn("previousStepClickedMouse context", self.body[:expand])


class TheBranchSaysWhatItSaw(unittest.TestCase):
    """`X was not found` cannot be diagnosed; `X was not found among Y` can."""

    def setUp(self):
        self.source = bot_elm()
        self.body = function_body(self.source, "routeToStationByName")

    def test_the_conclusion_prints_the_windows_contents(self):
        self.assertIn("describeSearchResultsContents", self.body)
        self.assertIn("diagnoseSearchResults", self.body)

    def test_the_waiting_states_print_them_too(self):
        # #64's other half: an operator watching a live trip should see the
        # window filling in, not only the post-mortem.
        self.assertGreaterEqual(
            self.body.count("describeProgress"), 4,
            "some state of this branch reports neither the counter nor the "
            "window contents")

    def test_the_status_line_carries_the_window_every_reading(self):
        self.assertIn("describeSearchResults context", self.source)
        described = function_body(self.source, "describeSearchResults")
        self.assertIn('""', described,
                      "the status line entry is not empty when no results "
                      "window is up, so every reading grows a dead field")

    def test_the_rendered_and_in_tree_counts_are_both_reported(self):
        # The pair is what settles #25's unverified virtualisation risk from a
        # log line instead of a live client.
        contents = function_body(self.source, "searchResultsContents")
        self.assertIn("getAllContainedDisplayTextsWithRegion", contents)
        self.assertIn("getAllContainedDisplayTexts ", contents)


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version` to
    whatever this machine's elm reports, and open `module Bot exposing (...)` to
    `(..)` so the repl can reach more than `botMain`.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-search-results-")
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
                  "import Common.Basics exposing (..)\n") + "".join(
            expression + "\n" for expression in expressions)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        answers = [answer == "True"
                   for answer in re.findall(r"(True|False) : Bool", plain)]
        return answers, plain, result.stderr

    def evaluate(self, expressions):
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def works(self):
        answers, plain, stderr = self.ask(
            ['searchQueryForStation "Amarr VIII (Oris) - Emperor Family Academy"'
             ' == "Emperor Family Academy"'])
        return answers == [True], plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def elm_is_available():
    return shutil.which("elm") is not None


def elm_list(texts):
    return "[ " + ", ".join('"%s"' % text.replace('"', '\\"')
                            for text in texts) + " ]"


def elm_contents(rendered, in_tree=None):
    return "{ rendered = %s, inTree = %s }" % (
        elm_list(rendered), elm_list(in_tree if in_tree is not None else rendered))


def elm_diagnosis(rendered, in_tree, group_offered):
    return 'diagnoseSearchResults { stationName = "%s", contents = %s, stationsGroupIsOffered = %s }' % (
        STATION_NAME, elm_contents(rendered, in_tree),
        "True" if group_offered else "False")


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheDiagnosesAreExecutedRatherThanMirrored(unittest.TestCase):
    """Four causes, four different sentences, decided from one reading.

    Issue #64 lists these as what the recording could not settle. They are the
    whole point of the change -- if two of them collapse into one sentence the
    next failure is as undiagnosable as run 17 was.
    """

    # The window as CLAUDE.md recorded it live, before the group is expanded.
    COLLAPSED = ["Search Results", "Corporations (1)", "Stations (26)"]

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

    def test_a_row_in_the_tree_and_not_rendered_is_named_as_scrolled_out(self):
        # #25's unverified risk, and the one cause that says what to do next.
        answers = self.repl.evaluate([
            '%s |> String.contains "scrolled out of view"'
            % elm_diagnosis(self.COLLAPSED, self.COLLAPSED + [RENDERED_ROW], True)])
        self.assertEqual([True], answers)

    def test_a_group_with_no_matching_row_blames_the_row_text(self):
        answers = self.repl.evaluate([
            '%s |> String.contains "does not carry the full name"'
            % elm_diagnosis(self.COLLAPSED, self.COLLAPSED, True)])
        self.assertEqual([True], answers)

    def test_a_window_with_too_few_rows_is_called_unfilled(self):
        answers = self.repl.evaluate([
            '%s |> String.contains "never filled in"'
            % elm_diagnosis(["Search Results"], ["Search Results"], False)])
        self.assertEqual([True], answers)

    def test_rows_without_a_stations_group_blames_the_query_or_the_label(self):
        answers = self.repl.evaluate([
            '%s |> String.contains "no \'Stations (\' group"'
            % elm_diagnosis(["Search Results", "Corporations (1)", "Agents (3)",
                             "Ashab", "Amarr"],
                            ["Search Results", "Corporations (1)", "Agents (3)",
                             "Ashab", "Amarr"], False)])
        self.assertEqual([True], answers)

    def test_the_four_sentences_are_four_different_sentences(self):
        cases = [
            elm_diagnosis(self.COLLAPSED, self.COLLAPSED + [RENDERED_ROW], True),
            elm_diagnosis(self.COLLAPSED, self.COLLAPSED, True),
            elm_diagnosis(["Search Results"], ["Search Results"], False),
            elm_diagnosis(["a", "b", "c", "d"], ["a", "b", "c", "d"], False),
        ]
        comparisons = []
        for first in range(len(cases)):
            for second in range(first + 1, len(cases)):
                comparisons.append("(%s) /= (%s)" % (cases[first], cases[second]))
        self.assertEqual([True] * len(comparisons),
                         self.repl.evaluate(comparisons))

    def test_the_full_name_really_is_a_substring_of_the_rendered_row(self):
        # Cause 3 of #67, settled: the colour markup ahead of the name and the
        # jump count behind it do not stop the match the branch performs, so a
        # row that renders in this form is found. If a future client form breaks
        # this, it breaks here rather than in a wind-down.
        answers = self.repl.evaluate([
            'stringContainsIgnoringCase "%s" "%s"'
            % (STATION_NAME, RENDERED_ROW.replace('"', '\\"'))])
        self.assertEqual([True], answers)


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheContentsPrintAsSomethingReadable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        usable, output = cls.repl.works()
        if not usable:
            cls.repl.close()
            raise unittest.SkipTest(
                "elm repl cannot evaluate here:\n" + output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_empty_window_reports_both_counts_and_no_rows(self):
        answers = self.repl.evaluate([
            'describeSearchResultsContents %s == "0 rendered of 0 in the tree"'
            % elm_contents([])])
        self.assertEqual([True], answers)

    def test_the_rows_are_quoted_verbatim(self):
        answers = self.repl.evaluate([
            'describeSearchResultsContents %s == "2 rendered of 2 in the tree: '
            '\'Search Results\', \'Stations (26)\'"'
            % elm_contents(["Search Results", "Stations (26)"])])
        self.assertEqual([True], answers)

    def test_the_two_counts_differ_when_rows_are_unrendered(self):
        # An expanded group of 26 stations with two rows rendered is what
        # virtualisation looks like in this line.
        answers = self.repl.evaluate([
            'describeSearchResultsContents %s |> String.startsWith '
            '"2 rendered of 26 in the tree"'
            % elm_contents(["row 1", "row 2"],
                           ["row %d" % index for index in range(1, 27)])])
        self.assertEqual([True], answers)

    def test_a_long_list_is_cut_short_and_says_so(self):
        rows = ["row %d" % index for index in range(1, 21)]
        answers = self.repl.evaluate([
            'describeSearchResultsContents %s |> String.endsWith ", ..."'
            % elm_contents(rows),
            'describeSearchResultsContents %s |> String.contains "\'row 20\'"'
            % elm_contents(rows)])
        self.assertEqual([True, False], answers)
