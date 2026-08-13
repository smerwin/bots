"""Tests for the two prerequisite gates themselves.

Issue #71. The harness that decides whether a case runs is the last place a
silent skip can be allowed to hide, so its own rules are asserted rather than
read: a missing toolchain raises, an absent corpus skips, and the probe that
decides "can this machine execute Elm at all" cannot be changed by anything
under test.

The structural case is the one that keeps this fixed. Eleven test files each
carried their own copy of the harness and their own smoke probe; within a day of
#71 being filed those copies had split into two dialects (#84 batched five of
them and left six alone). One copy is only one copy for as long as nothing adds
a twelfth, which is what `NoFileCarriesItsOwnHarness` is for.

Issue #172 added the second thing this file has to hold: one built app is handed
to every class in a process, so the cases that used to be "each class gets its
own scratch, nothing to say" are now about **shared mutable state**. What keeps
that safe is not that the classes are well behaved -- it is
`BuiltApp.check_unchanged`, asked on the way out and on the way back -- and the
cases below are the ones that fail if that check is loosened, removed, or made
to look past the one file a class wrote.

One class here needs `elm` and the rest do not: the toolchain cases substitute
what `open_repl` looks for rather than removing it, and the shared-build and
script-shape cases are about a fingerprint, a cache and a list of lines.
`TheFoldedQuestionIsTheSameQuestion` is the exception, and has to be -- what it
asserts is that the real compiler answers the same question the same way in both
shapes, which nothing but the real compiler can say.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import shutil
import tempfile
import unittest

import prerequisites

HERE = os.path.dirname(os.path.abspath(__file__))
MISSION_RUNNER_BOT_ELM = os.path.join(prerequisites.MISSION_RUNNER_DIR,
                                      "Bot.elm")


def suite_sources():
    """Every test module in this directory, bar this one.

    This file is excluded because it is the scanner: the patterns it looks for
    are written out here, so it would report itself.
    """
    return sorted(path for path in glob.glob(os.path.join(HERE, "test_*.py"))
                  if os.path.basename(path) != os.path.basename(__file__))


class AMissingToolchainIsNotASkip(unittest.TestCase):
    """The whole of #71 in one property.

    A skip means "there was nothing to report on". A toolchain that is not
    there means "the report was never made", and a run must not print those two
    the same way.
    """

    def setUp(self):
        self.which = prerequisites.shutil.which
        prerequisites.shutil.which = lambda name: None
        self.addCleanup(setattr, prerequisites.shutil, "which", self.which)
        os.environ.pop(prerequisites.MAY_SKIP_ENV, None)

    def test_it_raises_rather_than_skipping(self):
        with self.assertRaises(prerequisites.ElmToolchainMissing) as raised:
            prerequisites.open_repl()
        self.assertNotIsInstance(raised.exception, unittest.SkipTest)

    def test_the_error_says_how_to_fix_it(self):
        with self.assertRaises(prerequisites.ElmToolchainMissing) as raised:
            prerequisites.open_repl()
        self.assertIn("brew install elm", str(raised.exception))

    def test_the_escape_hatch_downgrades_it_to_a_named_skip(self):
        # Named, because CI matches on the reason -- see
        # `check_expected_skips.py`, which refuses this one.
        os.environ[prerequisites.MAY_SKIP_ENV] = "1"
        self.addCleanup(os.environ.pop, prerequisites.MAY_SKIP_ENV, None)
        with self.assertRaises(unittest.SkipTest) as raised:
            prerequisites.open_repl()
        self.assertEqual(str(raised.exception),
                         prerequisites.NO_TOOLCHAIN_SKIP_REASON)

    def test_the_hatch_is_off_unless_it_is_set_to_something(self):
        for value, expected in [("", False), ("0", False), ("1", True),
                                ("yes", True)]:
            with self.subTest(value=value):
                os.environ[prerequisites.MAY_SKIP_ENV] = value
                self.addCleanup(os.environ.pop, prerequisites.MAY_SKIP_ENV, None)
                self.assertEqual(prerequisites.may_skip_without_elm(), expected)


class TheProbeCannotDriftWithTheCodeUnderTest(unittest.TestCase):
    """Each of the eleven copies probed a real function's current behaviour.

    `missionNameForDeclining "x"` answering `"x" : String` was one of them, so
    changing that function disabled a whole file without a word. The probe now
    asks for a declaration the harness itself appends to the scratch copy.
    """

    def test_the_probe_name_appears_nowhere_in_the_checked_in_source(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
            self.assertNotIn(prerequisites.PROBE_NAME, source.read())

    def test_the_declaration_the_harness_appends_answers_the_probe(self):
        # The two halves are written apart -- a declaration and the string the
        # probe looks for -- so they are checked against each other.
        self.assertIn('"%s"' % prerequisites.PROBE_ANSWER,
                      prerequisites.PROBE_DECLARATION)
        self.assertIn("%s =" % prerequisites.PROBE_NAME,
                      prerequisites.PROBE_DECLARATION)

    def test_it_still_goes_through_bot_so_a_broken_app_cannot_pass_it(self):
        """The one thing the probe must remain coupled to.

        A probe on `1 + 1` cannot drift either, and would answer just as
        happily for an app that does not compile. This one is declared *in*
        `Bot.elm`, so it cannot be reached unless the app builds.
        """
        self.assertIn("elmReplHarnessProbe : String",
                      prerequisites.PROBE_DECLARATION)


class TheCorpusGateIsAThreeWayAnswer(unittest.TestCase):
    """Absent evidence skips; present evidence that disagrees must fail.

    Only the middle case is a skip, and the reason is stated so CI can tell it
    from a prerequisite the runner should have had.
    """

    def setUp(self):
        self.logs = tempfile.mkdtemp(prefix="test-recorded-runs-")
        self.addCleanup(shutil.rmtree, self.logs, True)
        real = prerequisites.EVE_BOT_LOGS
        prerequisites.EVE_BOT_LOGS = self.logs
        self.addCleanup(setattr, prerequisites, "EVE_BOT_LOGS", real)

    def record(self, name):
        path = os.path.join(self.logs, "mission_run%s.log" % name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# [1.0] (0s)\n")
        return path

    def test_no_recorded_run_skips_with_the_reason_stated(self):
        with self.assertRaises(unittest.SkipTest) as raised:
            prerequisites.recorded_runs("11", "17")
        self.assertIn("mission_run{11,17}.log", str(raised.exception))

    def test_the_runs_that_are_here_are_returned_and_the_rest_ignored(self):
        expected = self.record("11")
        self.assertEqual(prerequisites.recorded_runs("11", "17"),
                         [("11", expected)])

    def test_one_recorded_run_is_enough_to_stop_it_skipping(self):
        # The failure #78 found from the other side: a gate that answers on
        # what the *search* returned rather than on what evidence exists turns
        # "the corpus disagrees" into "there was no corpus", which reports a
        # finding where there is only an empty directory.
        self.record("21")
        self.assertEqual(len(prerequisites.recorded_runs("21")), 1)


class OneBuiltAppIsHandedToEveryClass(unittest.TestCase):
    """#172. The cache, and the check that makes sharing safe.

    The saving is real only because the tree has nothing per-class in it; the
    danger is that a class writes into it anyway and the next class compiles
    somebody else's edit. So the fingerprint is what these are about.
    """

    def setUp(self):
        self.built = dict(prerequisites._built_apps)
        prerequisites._built_apps.clear()
        self.addCleanup(prerequisites._built_apps.update, self.built)
        self.addCleanup(prerequisites._built_apps.clear)

    def tree(self, **files):
        """A directory shaped like a built app, with no elm anywhere near it."""
        path = tempfile.mkdtemp(prefix="test-built-app-")
        self.addCleanup(shutil.rmtree, path, True)
        for name, contents in files.items():
            full = os.path.join(path, name)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(contents)
        return path

    def test_the_same_app_is_built_once_and_handed_out_again(self):
        # The whole of the saving: 131 classes, one compile. A cache that
        # answered with a fresh build would be the shipped behaviour with more
        # code.
        builds = []

        class CountingBuild:
            def __init__(self, app_dir):
                builds.append(app_dir)
                self.app_dir = app_dir
                self.path = app_dir

        real = prerequisites.BuiltApp
        prerequisites.BuiltApp = CountingBuild
        self.addCleanup(setattr, prerequisites, "BuiltApp", real)

        first = prerequisites.built_app("/one")
        again = prerequisites.built_app("/one")
        other = prerequisites.built_app("/two")

        self.assertIs(first, again, "the second class must be handed the first "
                                    "class's built app, not a new one")
        self.assertIsNot(first, other)
        self.assertEqual(builds, ["/one", "/two"],
                         "one build per app, and the second app is its own")

    def test_an_edit_to_the_tree_moves_the_fingerprint(self):
        # The failure sharing introduces, and the one thing that must never be
        # quiet: the next class would compile this edit and report on it as the
        # bot's own source. What is done about it is the case below; this is
        # that the fingerprint can see it at all.
        app = self.tree(**{"Bot.elm": "module Bot exposing (..)\n"})
        fingerprint = prerequisites.fingerprint_of_app(app)
        bot = os.path.join(app, "Bot.elm")
        with open(bot, "a", encoding="utf-8") as handle:
            handle.write("\nsomethingAClassAdded = 1\n")

        after = prerequisites.fingerprint_of_app(app)
        self.assertNotEqual(after, fingerprint,
                            "an edit to the tree's source must move the "
                            "fingerprint, or nothing downstream can see it")

    def test_the_check_names_the_file_and_refuses_to_hand_the_tree_on(self):
        built = prerequisites.BuiltApp.__new__(prerequisites.BuiltApp)
        built.app_dir = "eve-online-mission-runner"
        built.path = self.tree(**{"Bot.elm": "module Bot exposing (..)\n",
                                  "elm.json": "{}\n"})
        built.fingerprint = prerequisites.fingerprint_of_app(built.path)
        built.check_unchanged("a class that changed nothing")

        with open(os.path.join(built.path, "Bot.elm"), "w",
                  encoding="utf-8") as handle:
            handle.write("module Bot exposing (..)\nedited = 1\n")

        with self.assertRaises(prerequisites.SharedAppChanged) as raised:
            built.check_unchanged("SomeClass.close")
        self.assertIn("Bot.elm", str(raised.exception))
        self.assertIn("SomeClass.close", str(raised.exception))

    def test_a_file_that_appears_or_disappears_counts_too(self):
        # Not only a changed file: a class that drops a module in, or removes
        # one, changes what the next compile sees just as much.
        built = prerequisites.BuiltApp.__new__(prerequisites.BuiltApp)
        built.app_dir = "app"
        built.path = self.tree(**{"Bot.elm": "module Bot exposing (..)\n"})
        built.fingerprint = prerequisites.fingerprint_of_app(built.path)

        added = os.path.join(built.path, "Extra.elm")
        with open(added, "w", encoding="utf-8") as handle:
            handle.write("module Extra exposing (..)\n")
        with self.assertRaises(prerequisites.SharedAppChanged) as raised:
            built.check_unchanged("added")
        self.assertIn("Extra.elm", str(raised.exception))

        os.remove(added)
        os.remove(os.path.join(built.path, "Bot.elm"))
        with self.assertRaises(prerequisites.SharedAppChanged) as raised:
            built.check_unchanged("removed")
        self.assertIn("Bot.elm", str(raised.exception))

    def test_the_compiler_writing_its_own_build_output_is_not_a_change(self):
        # `elm-stuff` is what `elm repl` is for. Counting it would report every
        # compile as tampering, which is a guard nobody could leave armed.
        app = self.tree(**{"Bot.elm": "module Bot exposing (..)\n",
                           "elm-stuff/0.19.1/i.dat": "before"})
        fingerprint = prerequisites.fingerprint_of_app(app)
        with open(os.path.join(app, "elm-stuff", "0.19.1", "i.dat"), "w",
                  encoding="utf-8") as handle:
            handle.write("after, and much longer than before")
        self.assertEqual(prerequisites.fingerprint_of_app(app), fingerprint,
                         "build output must not read as a class having "
                         "written into the shared tree")
        self.assertNotIn("elm-stuff/0.19.1/i.dat", fingerprint)
        self.assertIn("Bot.elm", fingerprint)

    def test_handing_a_repl_out_checks_the_tree_first(self):
        # The probe runs once per built app. What replaces the other 130 is
        # this check, so `open_repl` must ask it rather than assume it.
        asked = []

        class Watched:
            works = True
            probe_output = ""
            path = "/nowhere"

            def check_unchanged(self, what):
                asked.append(what)

        real = prerequisites.built_app
        prerequisites.built_app = lambda app_dir: Watched()
        self.addCleanup(setattr, prerequisites, "built_app", real)

        repl = prerequisites.open_repl()
        self.assertEqual(len(asked), 1,
                         "open_repl must check the tree it is handing over")
        repl.close()
        self.assertEqual(len(asked), 2,
                         "close must check it again, so the class that wrote "
                         "into it is the class that is named")

    def test_close_deletes_nothing_the_next_class_still_needs(self):
        # `tearDownClass` used to rmtree the class's own scratch. Against a
        # shared tree that would leave every later class compiling nothing.
        removed = []

        class Watched:
            works = True
            probe_output = ""
            path = "/nowhere"

            def check_unchanged(self, what):
                pass

            def remove(self):
                removed.append(self.path)

        real = prerequisites.built_app
        prerequisites.built_app = lambda app_dir: Watched()
        self.addCleanup(setattr, prerequisites, "built_app", real)

        real_rmtree = prerequisites.shutil.rmtree
        trees = []
        prerequisites.shutil.rmtree = lambda path, *a, **k: trees.append(path)
        self.addCleanup(setattr, prerequisites.shutil, "rmtree", real_rmtree)

        prerequisites.open_repl().close()
        self.assertEqual(trees, [], "close must not remove the shared tree")
        self.assertEqual(removed, [])


class TheBindingsRideInsideTheEntry(unittest.TestCase):
    """#172's second half: what a question costs is entries, not lines.

    An entry is a compile of the app's whole `Bot.elm`, so a preamble of six
    bindings used to charge six of them for one answer. These are about the
    shape of the script; that the shape still answers the same is
    `TheFoldedQuestionIsTheSameQuestion`, which asks the real compiler.
    """

    def repl(self, preamble):
        made = prerequisites.ElmRepl.__new__(prerequisites.ElmRepl)
        made.preamble = list(preamble)
        return made

    def test_a_question_with_no_bindings_is_two_entries(self):
        script = self.repl(["import Bot exposing (..)"]).script(["a", "b"])
        self.assertEqual(script, ["import Bot exposing (..)", "[ a, b ]"])

    def test_every_binding_travels_inside_the_one_entry(self):
        made = self.repl(["import Bot exposing (..)", "twice n = n * 2"])
        script = made.script(["twice 1"], definitions=["thrice n = n * 3"])
        self.assertEqual(script, [
            "import Bot exposing (..)",
            "let",
            "    twice n = n * 2",
            "    thrice n = n * 3",
            "in",
            "[ twice 1 ]",
            "",
        ])

    def test_a_binding_carrying_newlines_is_indented_line_by_line(self):
        # The defect the suite's first full run found. Callers hand over
        # bindings with newlines in them -- `reading_binding` writes two at once
        # -- and indenting only the first leaves the second at column zero,
        # where Elm reads the `let` as over. It answers `-- LET PROBLEM`, which
        # reaches the case as "answered 0 of 1" and is indistinguishable from
        # the rule under test having answered nothing.
        made = self.repl(["import Bot exposing (..)"])
        script = made.script(
            ["reading"],
            definitions=["reading = decode json\nrows = reading.rows"])
        self.assertEqual(script, [
            "import Bot exposing (..)",
            "let",
            "    reading = decode json",
            "    rows = reading.rows",
            "in",
            "[ reading ]",
            "",
        ])

    def test_the_entry_is_closed_so_the_repl_stops_waiting_for_more(self):
        # Without the blank line the repl sits in its continuation prompt until
        # stdin ends and prints no answer at all -- which arrives at the caller
        # as "answered 0 of N", indistinguishable from a rule that answered
        # nothing.
        made = self.repl(["import Bot exposing (..)", "twice n = n * 2"])
        script = made.script(["twice 1"])
        self.assertEqual(script[-1], "")
        self.assertIn("in", script)

    def test_imports_stay_entries_of_their_own(self):
        # A `let` cannot hold an import, so these are the one thing the fold
        # must leave alone -- and saxrat's preamble is four of them.
        preamble = ["import Bot exposing (..)",
                    "import EveOnline.MemoryReading",
                    "import EveOnline.ParseUserInterface"]
        script = self.repl(preamble).script(["a"])
        self.assertEqual(script[:3], preamble)
        self.assertNotIn("let", script)

    def test_a_value_expression_is_its_own_entry_and_carries_the_bindings(self):
        # `values` asks one expression per entry deliberately (#84). What #172
        # changes is only that its bindings ride inside those entries rather
        # than being entries themselves.
        made = self.repl(["import Bot exposing (..)", "twice n = n * 2"])
        fed = []
        made.run_script = lambda lines: (fed.append(list(lines)), ("", ""))[1]
        with self.assertRaises(AssertionError):
            made.values(["twice 1", "twice 2"], r"(\d+) : Int")
        self.assertEqual(fed[0], [
            "import Bot exposing (..)",
            "let", "    twice n = n * 2", "in", "twice 1", "",
            "let", "    twice n = n * 2", "in", "twice 2", "",
        ])


class TheFoldedQuestionIsTheSameQuestion(unittest.TestCase):
    """The fold asked of the real compiler, both ways, on one built app.

    Everything above is about the shape of the script. This is the one that
    would catch a fold that compiles and answers something else -- it asks the
    same question in the shape #172 replaced and in the shape it shipped, and
    requires the answers to agree. It is the only case in this file that needs
    `elm`, and it needs it the way every executing case does: a missing
    toolchain is an error here, never a skip.

    The bindings are over the harness's own probe declaration rather than over
    anything in `Bot.elm`, so a rename in the app cannot quietly empty this out.
    """

    BINDINGS = ["probeText = " + prerequisites.PROBE_NAME,
                "longerThan n text = String.length text > n"]
    EXPRESSIONS = ["longerThan 0 probeText",
                   "longerThan 10000 probeText",
                   "probeText == " + prerequisites.PROBE_NAME]

    @classmethod
    def setUpClass(cls):
        class Folded(prerequisites.ElmRepl):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.preamble = self.preamble + cls.BINDINGS

        cls.repl = prerequisites.open_repl(Folded)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_shapes_answer_the_same(self):
        folded = self.repl.evaluate(self.EXPRESSIONS)
        self.assertEqual(folded, [True, False, True],
                         "the shipped shape must answer the question")

        # The shape #172 replaced: every binding an entry of its own.
        plain, stderr = self.repl.run_script(
            list(self.repl.preamble)
            + ["[ %s ]" % ", ".join(self.EXPRESSIONS)])
        unfolded = [answer == "True" for answer in
                    prerequisites.ElmRepl.answers_in(
                        plain, prerequisites.BOOLEAN_ANSWER_IN_LIST)]
        self.assertEqual(
            folded, unfolded,
            "folding the bindings into the entry changed the answers.\n%s\n%s"
            % (plain, stderr))

    def test_the_fold_is_fewer_entries_than_the_shape_it_replaced(self):
        # The whole of the saving, stated as the relation rather than as a
        # duration: bindings stop being things the compiler is asked about.
        script = self.repl.script(self.EXPRESSIONS)
        entries = [line for line in script if line.startswith("import ")]
        self.assertEqual(
            len(entries) + 1, 2,
            "one import and one question is what a folded script asks for")
        self.assertLess(
            len(entries) + 1,
            len(self.repl.preamble) + 1,
            "the shape this replaced asked for one entry per binding")


class NoFileCarriesItsOwnHarness(unittest.TestCase):
    """One harness, and the assertion that it stays one.

    Eleven copies is how eleven probes drifted, and nothing structural stopped a
    twelfth. These read the test sources themselves.
    """

    def test_no_test_module_defines_its_own_repl_class(self):
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                if re.search(r"^class ElmRepl\b", source.read(), re.M):
                    offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these define their own harness rather than importing the shared "
            "one from prerequisites.py")

    def test_no_test_module_runs_elm_for_itself(self):
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                if re.search(r'subprocess\.run\(\s*\[\s*"elm"', source.read()):
                    offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these drive `elm` directly, so their cases are gated by whatever "
            "they decided for themselves rather than by open_repl")

    def test_no_test_module_decides_for_itself_whether_elm_is_available(self):
        # `@unittest.skipUnless(elm_is_available(), ...)` is the decorator that
        # turned an absent toolchain into a quiet skip in all eleven files.
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                text = source.read()
            if "elm_is_available" in text or re.search(
                    r'shutil\.which\(\s*"elm"', text):
                offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these answer the toolchain question themselves; open_repl owns it")

    def test_no_test_module_wraps_json_in_an_elm_literal_of_its_own(self):
        # Issue #174. Three files each dropped `json.dumps` output straight into
        # an Elm `"""..."""` string, and Elm eats the backslash escapes inside
        # one -- so every fixture holding a double quote decoded to `Nothing`
        # and the cases over it reported the parser answering nothing.
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                if re.search(r'"""\s*%s\s*"""', source.read()):
                    offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these build an Elm string literal by hand rather than through "
            "elm_json_literal, which is how a fixture comes to decode to "
            "nothing while its case still passes")

    def test_no_test_module_reaches_into_the_built_app(self):
        # #172's premise, checked rather than remembered. One tree is handed to
        # every class in a process, and that is safe exactly because what
        # differs between classes is `preamble` -- repl input -- and never the
        # directory. A module that names `.app` or `.scratch` is one that could
        # write into the tree the next class compiles, and `check_unchanged`
        # would then stop the suite rather than the reviewer.
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                text = source.read()
            if re.search(r"\.(app|scratch|built)\b", text):
                offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these reach for the built app's directory; the tree is shared by "
            "every class in the process, so writing into it decides what the "
            "others compile")

    def test_every_module_that_builds_a_reading_uses_the_shared_literal(self):
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                text = source.read()
            if ("decodeMemoryReadingFromString" in text
                    and "elm_json_literal" not in text):
                offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these hand the decoder a literal they escaped themselves")


if __name__ == "__main__":
    unittest.main()
