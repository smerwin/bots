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


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version` to
    whatever this machine's elm reports, build there and never in the checked-in
    source, and open `module Bot exposing (...)` to `(..)` so the repl can reach
    more than `botMain`.

    A file that needs more than this subclasses it -- a longer preamble, a
    helper that builds one kind of expression -- rather than copying it. Eleven
    copies is how eleven probes drifted.

    Construct it through `open_repl`, which is where the prerequisite is
    enforced; constructing it directly skips the probe.
    """

    def __init__(self, prefix="elm-repl-", preamble=DEFAULT_PREAMBLE,
                 app_dir=MISSION_RUNNER_DIR):
        self.preamble = list(preamble)
        self.scratch = tempfile.mkdtemp(prefix=prefix)
        self.app = os.path.join(self.scratch, "app")
        shutil.copytree(app_dir, self.app)

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
            handle.write(opened + PROBE_DECLARATION)

    def ask(self, expressions, definitions=()):
        """Everything the repl printed, plus one answer per expression.

        Asked as a single `[ a, b, c ]` rather than one expression per line,
        because the repl recompiles the module for every line it is given --
        #84 measured twenty expressions at 36.5s a line at a time against 5.8s
        as one list, and the answers come back in the order asked either way.
        That change reached five of the eleven copies of this class before this
        one replaced them; here every caller gets it.

        `definitions` are bindings the expressions need and are not answers, so
        a case's assertions line up with what it asked rather than with what it
        had to set up first. They stay one per line: they are few, and a `let`
        does not go in a list.
        """
        if not expressions:
            return [], "", ""
        plain, stderr = self.run_script(
            self.preamble + list(definitions) + ["[ %s ]" % ", ".join(expressions)])
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
        result = subprocess.run(
            ["elm", "repl"], cwd=self.app, capture_output=True, text=True,
            input="".join(line + "\n" for line in lines))
        return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout), result.stderr

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
        plain, stderr = self.run_script(
            self.preamble + list(definitions) + ["[ %s ]" % ", ".join(expressions)])
        answers = self.answers_in(plain, STRING_ANSWER_IN_LIST)
        self._require_one_answer_each(answers, expressions, plain, stderr)
        return [answer.replace('\\"', '"').replace("\\\\", "\\")
                for answer in answers]

    def values(self, expressions, pattern, definitions=()):
        """The repl's own printed answers, for the ones that are not `Bool`.

        Deliberately still one expression per line, unlike everything above:
        the caller matches the repl's printed form with its own pattern, and
        inside a list that form is the list's rather than each answer's. #84
        wrote this reason down after batching these broke six cases; it is kept
        here so the next reader does not "fix" it either.
        """
        plain, stderr = self.run_script(
            self.preamble + list(definitions) + list(expressions))
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

        Asks only for the declaration this module appended, so no mutation of
        the code under test can reach this answer. What it still proves is what
        matters: the declaration is in `Bot.elm`, so an app that does not
        compile cannot produce it.

        It runs its own script rather than the caller's preamble, so a file
        whose cases drive some other module is still asking the same question
        here as every other file.
        """
        plain, stderr = self.run_script(["import Bot", "Bot." + PROBE_NAME])
        return ('"%s" : String' % PROBE_ANSWER) in plain, plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def may_skip_without_elm():
    return os.environ.get(MAY_SKIP_ENV, "") not in ("", "0")


def open_repl(repl_class=ElmRepl, **kwargs):
    """A repl that has been shown to work, or a loud stop.

    Call this from `setUpClass`. It never returns a repl that cannot evaluate,
    and it never turns a broken toolchain into a quiet skip.
    """
    if shutil.which("elm") is None:
        if may_skip_without_elm():
            raise unittest.SkipTest(NO_TOOLCHAIN_SKIP_REASON)
        raise ElmToolchainMissing(
            "elm is not on PATH, so these cases would not execute the rules "
            "they exist to pin. That is a broken environment, not an absent "
            "one: %s" % INSTALL_HINT)

    repl = repl_class(**kwargs)
    works, output = repl.probe()
    if works:
        return repl

    repl.close()
    if may_skip_without_elm():
        raise unittest.SkipTest(NO_TOOLCHAIN_SKIP_REASON + ":\n" + output)
    raise ElmToolchainMissing(
        "elm is on PATH but `elm repl` could not evaluate the harness's own "
        "probe, so nothing below would have run. Either the app does not "
        "compile or the toolchain cannot build here (no cached dependencies, "
        "no writable ELM_HOME). %s\n%s" % (INSTALL_HINT, output))
