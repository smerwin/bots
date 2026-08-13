"""What a case needs before it can run, and what to do when it is not there.

Two prerequisites in this suite are outside the code under test. A case that
executes Elm needs the toolchain (`elm` on PATH, its dependencies fetched); a
case that reads what the client wrote needs the recorded runs in
`~/eve-bot-logs`. Both were handled per file, eleven copies of one and several
spellings of the other, and the two answers had drifted apart.

**They are not the same kind of prerequisite and must not get the same answer.**

    situation                                   answer
    ------------------------------------------  ------------------------------
    evidence present, says what a case asserts   pass
    evidence absent                              skip, with a stated reason
    evidence present, does not say it            fail
    the machinery to run the case is missing     **error** -- never a skip

The corpus is *evidence a case reads*: absent, the case has nothing to report
on, and a suite that goes red for "no data" teaches people to ignore red. The
toolchain is *the machinery that executes the case*: absent, the rule under test
still exists and is simply not being checked, and the run says `OK` having
checked less than it appears to. That is this repo's signature bug wearing the
test suite's clothes -- and it has already cost something. #71: a mutation of
`<=` to `<` flipped a file's own smoke probe, seventeen cases were skipped, the
suite reported `OK`, and the rule the cases exist to pin was never executed.

So a missing toolchain raises `ElmToolchainMissing`, which `unittest` reports as
an error and which fails the run. `ELM_HARNESS_MAY_SKIP=1` downgrades it to a
skip for anyone who genuinely wants the Python half of the suite on a machine
with no Elm -- and that skip carries `NO_TOOLCHAIN_SKIP_REASON`, which
`check_expected_skips.py` refuses, so it cannot pass CI.

**The probe cannot drift with the code under test.** Each of the eleven copies
probed a real function's current behaviour -- `missionNameForDeclining "x"`
answering `"x" : String`, `missionTravelStepIsDock "Dock"` answering `True` --
so changing that function disabled the whole file quietly. (#92 has since
renamed that second one out of existence, which is the same hazard arriving on
schedule.) The probe here is a
declaration this module appends to the *scratch* copy of `Bot.elm` and asks for
by name. Nothing in the checked-in source can change its answer, and it still
proves what it has to prove: it lives in `Bot.elm`, so a `Bot.elm` that does not
compile cannot answer it.

**One built app per source directory per process, not one per class.** Issue
#172. Every class that executes Elm used to copy the whole app to its own
scratch directory and start an `elm repl` there, which compiles the app and its
dependencies from source into an `elm-stuff` the class then deleted -- 131 times
over a full run, sharing nothing but `~/.elm`'s *package* cache.

Profiled rather than assumed, which is what the issue asked for first, and the
answer moved the ordering. Over a six-module subset on one container, the 18
per-class builds cost **95 s** between them and `copytree` was **0.5 s** of that
-- 0.03 s each. The copy the issue leads with was never the cost; the compile
behind it was. Sharing one build per app took that subset from **763 s to
646 s**, and the two builds that replaced the eighteen cost 9 s. Real, and a
sixth of the problem rather than the whole of it: the rest is in
`ElmRepl.script`, where the same profile said the time actually goes.

`built_app` therefore builds the tree once per app per process and hands the
same directory to every `ElmRepl` that asks for that app. What differs between
classes is `preamble`, which is repl *input* rather than tree content, so there
was nothing per-class in the tree to begin with -- checked rather than assumed:
no test module names `.app` or `.scratch` at all, and the only two `app_dir`
values in the suite are the two maintained apps.

**Sharing mutable state between classes is exactly the trade this repo refuses
to make on faith, so the tree's stillness is checked at run time rather than
asserted.** `fingerprint_of_app` hashes every file in the tree except
`elm-stuff`, which is build output `elm repl` rewrites by design; that
fingerprint is taken the moment the build's probe passes, re-checked each time
the tree is handed to a class, and again in that class's `close`. A class that
writes into the tree fails in its own `tearDownClass` naming itself, rather
than handing the next class a `Bot.elm` it did not compile. That is also what
keeps the probe honest: it runs once per built app rather than once per class,
and what makes "probed once" as strong as "probed each time" is that the tree
handed over is byte for byte the tree that probed.

**Per process rather than per session.** `elm repl` writes `elm-stuff` as it
compiles, and two of them in one directory would be two writers of one build
cache; a worker process runs its cases one at a time, so within a process there
is no second writer. `pytest -n auto` gives each worker its own build, which is
one compile per worker rather than one per class, and is why the workflow's
`--dist loadfile` comment no longer describes the cost it was written for -- see
`.github/workflows/build-and-test.yml`.
"""
import atexit
import hashlib
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

EVE_BOT_LOGS = os.path.join(os.path.expanduser("~"), "eve-bot-logs")

# The escape hatch, and the reason it leaves behind. Both are named constants
# because `check_expected_skips.py` matches on the reason: a run that took this
# route says so in words, on every case it skipped, and CI reads them.
MAY_SKIP_ENV = "ELM_HARNESS_MAY_SKIP"
NO_TOOLCHAIN_SKIP_REASON = (
    "no elm toolchain, and %s is set -- these rules are NOT checked by "
    "execution in this run" % MAY_SKIP_ENV)

INSTALL_HINT = (
    "`brew install elm` (see CLAUDE.md, 'Elm toolchain' -- not `npm install`). "
    "Set %s=1 to skip these cases instead, which CI rejects." % MAY_SKIP_ENV)

# The probe. A declaration appended to the scratch `Bot.elm`, so its answer is
# fixed here rather than by anything under test.
PROBE_NAME = "elmReplHarnessProbe"
PROBE_ANSWER = "elm-repl-harness-can-evaluate"
PROBE_DECLARATION = "\n\n%s : String\n%s =\n    \"%s\"\n" % (
    PROBE_NAME, PROBE_NAME, PROBE_ANSWER)

DEFAULT_PREAMBLE = ("import Bot exposing (..)",)

BOOLEAN_ANSWER_IN_LIST = r"True|False"
STRING_ANSWER_IN_LIST = r'"((?:[^"\\]|\\.)*)"'
# A single answer with its own type annotation, for `values` -- the one caller
# that still asks line by line.
STRING_ANSWER = r'"((?:[^"\\]|\\.)*)"\s*: String'


class ElmToolchainMissing(Exception):
    """The machinery to execute a case is not here.

    Deliberately not a `SkipTest`. A skip means "there was nothing to report
    on"; this means "the report was never made", and the two must not print the
    same way.
    """


def recorded_runs(*names):
    """The runs among `names` this machine has, or a skip if it has none.

    Three situations, three different answers, and only the middle one is a
    skip:

    - the corpus is here and says something -> assert on it;
    - **the corpus is absent**, as it is on CI -> skip, with the reason stated.
      A case cannot report on evidence it cannot read, and a suite that goes red
      for "no data" teaches people to ignore red;
    - the corpus is here and does *not* say what a case asserts -> **fail**,
      because that is the evidence for a change having disappeared.

    This is a helper rather than three lines at each call site because the
    natural shape gets it wrong. Skipping missing files *inside* the loop and
    then asserting on whatever accumulated silently turns the third case into
    the second when the loop finds nothing at all: the assertion fires on an
    empty result and reports a finding where there is only an empty directory.
    CI caught exactly that, on a case that passed here.
    """
    found = [(name, os.path.join(EVE_BOT_LOGS, "mission_run%s.log" % name))
             for name in names]
    found = [pair for pair in found if os.path.exists(pair[1])]
    if not found:
        raise unittest.SkipTest(
            "none of mission_run{%s}.log is on this machine, so the recorded "
            "runs cannot be consulted here" % ",".join(names))
    return found


def elm_json_literal(value):
    """`value`'s JSON, as an Elm literal the decoder gets back byte for byte.

    **Elm processes backslash escapes inside a triple-quoted string too**, so
    the obvious `'\"\"\"%s\"\"\"' % json.dumps(value)` does not round-trip: a
    fixture whose JSON carries `\\"` -- which is every fixture holding a double
    quote, and this client's own route label is `alt="Next System in Route"` --
    reached the decoder as a bare `"`, the JSON was malformed, and the reading
    decoded to `Nothing`.

    That failure is the expensive kind rather than a broken fixture. A case over
    such a reading reports *the parser answering nothing* where the truth is
    *the fixture never arrived*, and the two are indistinguishable from outside:
    a rule that correctly answers `Nothing` for absent input passes, and so does
    a rule that would have answered something for input it never received.
    Issue #174 is the sweep of what that had been quietly costing.

    Encoding twice is what closes it, and the two escape vocabularies agree on
    everything the inner call can emit. `json.dumps` of an ASCII string produces
    only `\\"` and `\\\\`, which Elm reads exactly as JSON does. The one form
    they spell differently is `\\uXXXX` (Elm wants `\\u{XXXX}`), and the inner
    call has already turned every non-ASCII character into one, so the outer
    call escapes its backslash and Elm never meets the form it cannot read.
    """
    return json.dumps(json.dumps(value))


def elm_triple_quoted_json_literal(value):
    """The construction `elm_json_literal` replaced, kept so a case can run it.

    It is here rather than in the case that needs it because that case is the
    only thing in the suite allowed to build one, and
    `NoFileCarriesItsOwnHarness` refuses the shape everywhere else. Nothing may
    use this to build a fixture.
    """
    return '"""%s"""' % json.dumps(value)


class SharedAppChanged(Exception):
    """The tree a class was handed is not the tree that was built and probed.

    Deliberately not an assertion the suite can pass over. One built app per
    process is a saving only for as long as nothing writes into it; the moment
    something does, the next class compiles a `Bot.elm` it did not ask for and
    every answer after that is about somebody else's edit. That is this repo's
    signature failure with the suite as its subject, so it stops the class that
    caused it rather than being reported by whichever class notices later.
    """


BUILD_OUTPUT_DIRECTORY = "elm-stuff"


def fingerprint_of_app(app):
    """What every file in `app` holds, `elm-stuff` aside.

    `elm-stuff` is excluded because it is exactly what `elm repl` is *for* --
    build output it rewrites on every compile -- and including it would report
    the compiler doing its job as a class having tampered with the tree.
    Everything else is source the build was made from, so a difference here is a
    difference in what the next class would compile.
    """
    digests = {}
    for directory, subdirectories, names in os.walk(app):
        subdirectories[:] = [name for name in subdirectories
                             if name != BUILD_OUTPUT_DIRECTORY]
        for name in names:
            path = os.path.join(directory, name)
            with open(path, "rb") as handle:
                digests[os.path.relpath(path, app)] = hashlib.sha1(
                    handle.read()).hexdigest()
    return digests


def probe_app(app):
    """Whether an `elm repl` in `app` can evaluate -- not what it answered.

    Asks only for the declaration this module appends, so no mutation of the
    code under test can reach this answer. What it still proves is what matters:
    the declaration is in `Bot.elm`, so an app that does not compile cannot
    produce it.

    A module function rather than an `ElmRepl` method because the build has to
    ask it before any class holds a repl, and both must ask the same question.
    """
    plain, stderr = run_elm_repl(app, ["import Bot", "Bot." + PROBE_NAME])
    return ('"%s" : String' % PROBE_ANSWER) in plain, plain + "\n" + stderr


def run_elm_repl(app, lines):
    """One repl session over `lines` in `app`, colour codes stripped."""
    result = subprocess.run(
        ["elm", "repl"], cwd=app, capture_output=True, text=True,
        input="".join(line + "\n" for line in lines))
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout), result.stderr


class BuiltApp:
    """One scratch copy of one app, built once and handed to every class.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version` to
    whatever this machine's elm reports, build there and never in the checked-in
    source, and open `module Bot exposing (...)` to `(..)` so the repl can reach
    more than `botMain`. Then probe it, and remember what the tree held at the
    moment the probe passed.

    Everything about handing one tree to many classes rests on that fingerprint,
    which is why it is taken here and checked on the way out and back rather
    than being a property somebody asserted once.
    """

    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.scratch = tempfile.mkdtemp(
            prefix="elm-repl-%s-" % os.path.basename(app_dir.rstrip(os.sep)))
        self.path = os.path.join(self.scratch, "app")
        shutil.copytree(app_dir, self.path)

        version = subprocess.run(
            ["elm", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
        elm_json = os.path.join(self.path, "elm.json")
        with open(elm_json, encoding="utf-8") as source:
            patched = source.read().replace(
                '"elm-version": "0.19.1"', '"elm-version": "%s"' % version)
        with open(elm_json, "w", encoding="utf-8") as target:
            target.write(patched)

        bot = os.path.join(self.path, "Bot.elm")
        with open(bot, encoding="utf-8") as handle:
            source = handle.read()
        opened = re.sub(r"module Bot exposing\s*\([^)]*\)",
                        "module Bot exposing (..)", source, count=1)
        assert opened != source, "could not open Bot.elm's exports"
        with open(bot, "w", encoding="utf-8") as handle:
            handle.write(opened + PROBE_DECLARATION)

        self.works, self.probe_output = probe_app(self.path)
        self.fingerprint = fingerprint_of_app(self.path)

    def check_unchanged(self, what):
        """Raise unless the tree still holds what it held when it was probed."""
        current = fingerprint_of_app(self.path)
        if current == self.fingerprint:
            return
        changed = sorted(
            set(current) ^ set(self.fingerprint)
            | {name for name in set(current) & set(self.fingerprint)
               if current[name] != self.fingerprint[name]})
        raise SharedAppChanged(
            "%s: the built copy of %s is no longer what was compiled and "
            "probed -- %s. Every class in this process is handed this tree, so "
            "one that writes into it decides what the others compile."
            % (what, os.path.basename(self.app_dir), ", ".join(changed)))

    def remove(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


_built_apps = {}


def built_app(app_dir):
    """The built copy of `app_dir` for this process, building it if need be.

    One per app rather than one per class -- see this module's own docstring for
    what that costs and what checks it.
    """
    built = _built_apps.get(app_dir)
    if built is None:
        built = BuiltApp(app_dir)
        _built_apps[app_dir] = built
    return built


@atexit.register
def _remove_built_apps():
    for built in _built_apps.values():
        built.remove()


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    A view onto the process's `BuiltApp` for one app, plus this class's own
    `preamble`. It builds nothing: the tree was copied, patched and compiled
    once (see `BuiltApp`), and what makes one class's repl different from
    another's is the lines it feeds in, never the directory it feeds them to.

    A file that needs more than this subclasses it -- a longer preamble, a
    helper that builds one kind of expression -- rather than copying it. Eleven
    copies is how eleven probes drifted.

    Construct it through `open_repl`, which is where the prerequisite is
    enforced; constructing it directly skips the probe.

    `prefix` named the per-class scratch directory that no longer exists. It is
    still accepted because some fifty call sites pass one and a sweep of them
    would collide with every branch in flight, but it names nothing now: the
    scratch directory is named after the app, since there is one of it.
    """

    def __init__(self, prefix="elm-repl-", preamble=DEFAULT_PREAMBLE,
                 app_dir=MISSION_RUNNER_DIR):
        self.preamble = list(preamble)
        self.built = built_app(app_dir)
        self.app = self.built.path

    def script(self, expressions, definitions=()):
        """The lines one question costs, which is what the suite's time is.

        #84 established the first half: ask for `[ a, b, c ]` rather than one
        expression per line, because the repl recompiles for every *entry* it is
        given. Issue #172 measured what that costs and found the same charge
        being paid on the bindings. On this container an entry against the
        mission runner's 21,705-line `Bot.elm` costs about **1.5 s** whether it
        holds one expression or ten -- an empty session is 0.02 s, `import Bot`
        alone is 1.55 s, and each entry after it adds much the same again -- so
        a question asked with a preamble of bindings and three definitions was
        paying six compiles to answer one list.

        So every binding travels **inside the expression**, as one `let ... in`
        entry, and only the imports stay entries of their own (a `let` cannot
        hold one). The same six-module subset, asking the same 94 questions,
        went from **646 s to 343 s**. Note the folded script has *more* lines
        than the one it replaced -- `let`, `in`, and the blank that closes the
        entry -- which is the measurement's own evidence that what is being
        paid for is entries and not lines.

        `definitions` are bindings the expressions need and are not answers, so
        a case's assertions still line up with what it asked rather than with
        what it had to set up first -- nothing about a caller changes here, and
        a binding that will not sit in a `let` fails as a compile error the
        caller sees rather than as a wrong answer.
        """
        imports, bindings = self.imports_and_bindings(definitions)
        return imports + self.entry("[ %s ]" % ", ".join(expressions), bindings)

    def imports_and_bindings(self, definitions):
        """The preamble split into what must be an entry and what need not be.

        An `import` cannot sit in a `let`, so those stay entries of their own.
        Everything else a caller wrote -- a subclass's `BINDINGS`, a case's
        `definitions` -- is a binding, and rides inside the one entry that asks
        the question.
        """
        imports = [line for line in self.preamble if line.startswith("import ")]
        bindings = [line for line in self.preamble
                    if not line.startswith("import ")] + list(definitions)
        return imports, bindings

    @staticmethod
    def entry(expression, bindings):
        """One thing for the repl to compile: `expression`, given `bindings`.

        **Every physical line of a binding is indented, not every binding.** A
        caller is free to hand over a string carrying newlines -- two bindings
        written together, or one with a continuation -- and indenting only the
        first line leaves the rest at column zero, where Elm reads it as the
        `let` having ended. The suite found that on its first full run: the repl
        answered `-- LET PROBLEM`, which arrives at a case as "answered 0 of 1"
        and looks exactly like the rule under test returning nothing. Adding the
        same indent to each line keeps whatever relative shape the caller wrote.
        """
        if not bindings:
            return [expression]
        indented = ["    " + line
                    for binding in bindings
                    for line in binding.split("\n")]
        # The blank line is what closes a multi-line entry: without it the repl
        # sits in its continuation prompt until stdin ends and answers nothing,
        # which reads exactly like a rule that returned no answers.
        return ["let"] + indented + ["in", expression, ""]

    def ask(self, expressions, definitions=()):
        """Everything the repl printed, plus one answer per expression."""
        if not expressions:
            return [], "", ""
        plain, stderr = self.run_script(self.script(expressions, definitions))
        return self.answers_in(plain, BOOLEAN_ANSWER_IN_LIST), plain, stderr

    @staticmethod
    def answers_in(plain, pattern):
        """The elements of the last list the repl printed, by `pattern`.

        The repl wraps a long answer, so the `: List ...` annotation can land
        on the line after the closing bracket and an element can be on a line
        of its own. Newlines are collapsed before matching for that reason.

        The *last* list, because a `definitions` binding can itself print one
        and the expressions are always asked after them.

        **The opening bracket is found by balancing, not by a non-greedy
        match**, and that is the whole of this function's difficulty. A
        `definitions` binding that prints a large record -- a whole parsed
        `ReadingFromGameClient`, say -- puts hundreds of `[` and of the words
        `True` and `False` between the prompt and the real answer. A
        `\\[(.*?)\\]\\s*:\\s*List ` match then starts at some bracket *inside*
        that record and runs to the answer's own closing bracket, so the
        elements it yields are the record's fields followed by the answers.
        Measured: three expressions came back as nineteen.

        That is worse than an error, because `_require_one_answer_each` only
        checks the *count*. Ask for sixteen expressions after such a binding and
        the counts can agree while every answer read is a field of the record --
        a case that passes having tested nothing, which is this repo's signature
        bug wearing the test suite's clothes.
        """
        flat = plain.replace("\n", " ")
        closes = list(re.finditer(r"\]\s*:\s*List ", flat))
        if not closes:
            return []
        end = closes[-1].start()
        depth = 0
        for index in range(end, -1, -1):
            if flat[index] == "]":
                depth += 1
            elif flat[index] == "[":
                depth -= 1
                if depth == 0:
                    return re.findall(pattern, flat[index + 1:end])
        return []

    def run_script(self, lines):
        """One repl session over `lines`, with the colour codes stripped."""
        return run_elm_repl(self.app, lines)

    def evaluate(self, expressions, definitions=()):
        """Answer each expression, which must evaluate to a `Bool`."""
        answers, plain, stderr = self.ask(expressions, definitions)
        self._require_one_answer_each(answers, expressions, plain, stderr)
        return [answer == "True" for answer in answers]

    # The name half the suite used for the same thing.
    booleans = evaluate

    def strings(self, expressions, definitions=()):
        """Answer each expression, which must evaluate to a `String`."""
        if not expressions:
            return []
        plain, stderr = self.run_script(self.script(expressions, definitions))
        answers = self.answers_in(plain, STRING_ANSWER_IN_LIST)
        self._require_one_answer_each(answers, expressions, plain, stderr)
        return [answer.replace('\\"', '"').replace("\\\\", "\\")
                for answer in answers]

    def values(self, expressions, pattern, definitions=()):
        """The repl's own printed answers, for the ones that are not `Bool`.

        Deliberately still one expression per entry, unlike everything above:
        the caller matches the repl's printed form with its own pattern, and
        inside a list that form is the list's rather than each answer's. #84
        wrote this reason down after batching these broke six cases; it is kept
        here so the next reader does not "fix" it either.

        The bindings still travel *inside* each entry rather than as entries of
        their own (#172), which costs nothing here -- the entries are the
        expressions either way -- and removes a hazard as well as a compile: a
        binding asked as its own entry makes the repl print it, and
        `<function> : number -> number`, or a whole printed record, is one more
        thing a caller's pattern can match by accident.
        """
        imports, bindings = self.imports_and_bindings(definitions)
        lines = list(imports)
        for expression in expressions:
            lines += self.entry(expression, bindings)
        plain, stderr = self.run_script(lines)
        answers = re.findall(pattern, plain)
        self._require_one_answer_each(answers, expressions, plain, stderr)
        return answers

    @staticmethod
    def _require_one_answer_each(answers, expressions, plain, stderr):
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\n"
                "stderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))

    def probe(self):
        """Whether the repl can evaluate here at all -- not what it answered.

        It runs its own script rather than the caller's preamble, so a file
        whose cases drive some other module is still asking the same question
        here as every other file. `probe_app` is the shared question, asked
        once per built app and again by anything that wants to re-ask it.
        """
        return probe_app(self.app)

    def close(self):
        """Give the tree back, having checked this class did not change it.

        There is nothing to delete -- the tree outlives every class and is
        removed at process exit -- so what a `tearDownClass` buys instead is a
        checkpoint: a class that wrote into the shared tree is named here, by
        its own teardown, rather than being found by whichever class compiles
        next.
        """
        self.built.check_unchanged(
            "%s.close" % type(self).__name__)


def may_skip_without_elm():
    return os.environ.get(MAY_SKIP_ENV, "") not in ("", "0")


def open_repl(repl_class=ElmRepl, **kwargs):
    """A repl that has been shown to work, or a loud stop.

    Call this from `setUpClass`. It never returns a repl that cannot evaluate,
    and it never turns a broken toolchain into a quiet skip.

    The probe runs once per built app rather than once per class, and what
    replaces the other 130 of them is not trust but `check_unchanged`: the tree
    this hands over is asserted to be byte for byte the tree that answered the
    probe. Where it is not, nothing is handed over at all.
    """
    if shutil.which("elm") is None:
        if may_skip_without_elm():
            raise unittest.SkipTest(NO_TOOLCHAIN_SKIP_REASON)
        raise ElmToolchainMissing(
            "elm is not on PATH, so these cases would not execute the rules "
            "they exist to pin. That is a broken environment, not an absent "
            "one: %s" % INSTALL_HINT)

    repl = repl_class(**kwargs)
    if repl.built.works:
        repl.built.check_unchanged("open_repl(%s)" % repl_class.__name__)
        return repl

    output = repl.built.probe_output
    if may_skip_without_elm():
        raise unittest.SkipTest(NO_TOOLCHAIN_SKIP_REASON + ":\n" + output)
    raise ElmToolchainMissing(
        "elm is on PATH but `elm repl` could not evaluate the harness's own "
        "probe, so nothing below would have run. Either the app does not "
        "compile or the toolchain cannot build here (no cached dependencies, "
        "no writable ELM_HOME). %s\n%s" % (INSTALL_HINT, output))
