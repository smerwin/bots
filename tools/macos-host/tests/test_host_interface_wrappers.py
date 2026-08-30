"""Every app imports an interface the host has a wrapper for, in all three copies.

`eve-online-wingus` was the last bot on `BotLab.BotInterface_To_Host_2023_02_06`
and was retired with it, taking `Main_2023_02_06.elm` and the host code that
existed only for that interface -- see `notes/retire-wingus.md`. What is left is
one wrapper, and this file is what stops that becoming a silent constraint.

**The rule that picks a wrapper exists in three places and nothing compared
them.** `botlab_host.py`'s `MAIN_ELM_TEMPLATE_BY_INTERFACE`, `compile_bot.sh`'s
`main_elm_for`, and `.github/workflows/build-and-test.yml`'s own `case` -- and
all three carry a comment telling the next person to keep them in step, which is
exactly the shape this repo has paid for before: a claim kept as prose that no
test executes. Two of them can drift from the host without any bot failing to
build, because they *are* the build in CI and by hand respectively; the host is
the one that matters at run time and the one nobody exercises until a launch.

**A one-armed `case` is the guard, not dead weight.** Each of the three now has
a single arm, and collapsing any of them into an unconditional
"use `Main.elm`" would remove the only thing that makes an unsupported interface
fail *by name*: `prepare_build_dir` raises `no Main.elm wrapper for host
interface ...`, `compile_bot.sh` prints `no wrapper for its host interface,
skipped`, and the CI job emits an error. Compiling a bot against a wrapper it is
not typed against is the failure those refusals exist for, and it does not
present as a wrapper problem -- it presents as an `elm make` type error in
somebody else's app.

**Executed rather than read, where it can be.** The host's refusal is run
through the real `prepare_build_dir` against a throwaway app directory, because
a source read of the `raise` cannot say the raise is reachable. The two shell
copies are read, since there is nothing to run them against here.

Nothing here reads a live game client, a bot, or the recorded runs, and nothing
here needs `elm`.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlab_host"))

import botlab_host  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
APPLICATIONS_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online")
COMPILE_BOT_SH = os.path.join(MACOS_HOST_DIR, "compile_bot.sh")
WORKFLOW = os.path.join(
    REPO_DIR, ".github", "workflows", "build-and-test.yml")

# The one interface every app in the tree is on. Written out so that an app
# arriving on another one has to come past a named case rather than through a
# `case` arm somebody quietly added in one of the three copies.
CURRENT_INTERFACE = "BotLab.BotInterface_To_Host_2024_10_19"


def eve_apps():
    return sorted(
        name for name in os.listdir(APPLICATIONS_DIR)
        if os.path.isfile(os.path.join(APPLICATIONS_DIR, name, "Bot.elm")))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def case_arms(text, marker):
    """The interfaces a shell `case` over the grep result has an arm for.

    Both shell copies write the arm as `BotLab.BotInterface_To_Host_X) ...`, so
    the arms are the interface names that appear immediately before a `)`.
    """
    block = text[text.index(marker):]
    block = block[:block.index("esac")]
    return sorted(set(re.findall(
        r"(BotLab\.BotInterface_To_Host_[0-9_]+)\)", block)))


class EveryAppIsOnAnInterfaceTheHostCarries(unittest.TestCase):
    """The property the removal rests on, asked of the tree rather than assumed.

    `notes/retire-wingus.md` could delete one wrapper only because no app needed
    it. This is what says that stays true -- and it reads each app's own
    `import` rather than the interface modules the app vendors, which is
    `host_interface_of_bot`'s own rule: a vendored tree can carry a module its
    `botMain` is not typed against.
    """

    def test_every_app_imports_an_interface_with_a_wrapper(self):
        for app in eve_apps():
            with self.subTest(app):
                interface = botlab_host.host_interface_of_bot(
                    os.path.join(APPLICATIONS_DIR, app))
                self.assertIn(
                    interface, botlab_host.MAIN_ELM_TEMPLATE_BY_INTERFACE,
                    "%s imports %r and this host has no wrapper for it, so a "
                    "launch refuses by name -- either the app moved or a "
                    "wrapper was removed with something still using it"
                    % (app, interface))

    def test_every_app_is_on_the_one_current_interface(self):
        # Weaker than the case above in the sense that matters (that one is the
        # host's own question) and stronger in the sense a reader wants: it
        # names the interface, so an app arriving on a second one is a decision
        # somebody argues for rather than a wrapper map that quietly grew.
        self.assertEqual(
            {app: botlab_host.host_interface_of_bot(
                os.path.join(APPLICATIONS_DIR, app)) for app in eve_apps()},
            {app: CURRENT_INTERFACE for app in eve_apps()})

    def test_every_wrapper_the_map_names_exists(self):
        for interface, path in \
                botlab_host.MAIN_ELM_TEMPLATE_BY_INTERFACE.items():
            with self.subTest(interface):
                self.assertTrue(
                    os.path.isfile(path),
                    "the map offers a wrapper for %s at %s and there is no "
                    "such file, so a bot on that interface fails at `elm make` "
                    "rather than at the refusal written for it"
                    % (interface, path))


class TheThreeCopiesOfTheRuleAgree(unittest.TestCase):
    """`botlab_host.py`, `compile_bot.sh` and the CI job, compared.

    Each carries a comment saying to keep the three in step. That is the kind of
    claim this repo keeps as a test rather than as prose, because a drift here
    is silent in the worst direction: the two shell copies are what a developer
    and CI build with, so a wrapper they choose and the host does not is a
    green build for something no run would ever produce.
    """

    def test_compile_bot_sh_offers_the_same_interfaces_as_the_host(self):
        self.assertEqual(
            case_arms(source_of(COMPILE_BOT_SH), "main_elm_for()"),
            sorted(botlab_host.MAIN_ELM_TEMPLATE_BY_INTERFACE))

    def test_the_ci_job_offers_the_same_interfaces_as_the_host(self):
        self.assertEqual(
            case_arms(source_of(WORKFLOW), 'case "$iface" in'),
            sorted(botlab_host.MAIN_ELM_TEMPLATE_BY_INTERFACE))

    def test_each_copy_names_the_same_wrapper_file(self):
        wrapper = os.path.basename(
            botlab_host.MAIN_ELM_TEMPLATE_BY_INTERFACE[CURRENT_INTERFACE])
        self.assertEqual(wrapper, "Main.elm")
        for path in (COMPILE_BOT_SH, WORKFLOW):
            with self.subTest(os.path.basename(path)):
                self.assertIn(wrapper, source_of(path))

    def test_no_copy_still_names_a_wrapper_the_host_has_dropped(self):
        """The reintroduction this change would otherwise not notice.

        A wrapper file removed from the map but left named in a shell copy is a
        build that succeeds on a file that is not there -- or, worse, a build
        that succeeds against a *restored* wrapper the host would never choose.
        """
        gone = "Main_2023_02_06.elm"
        self.assertFalse(
            os.path.exists(os.path.join(
                MACOS_HOST_DIR, "botlab_host", gone)),
            "%s is back; if that is deliberate the host's own map has to name "
            "it too, and this file's other cases are what say so" % gone)
        for path in (COMPILE_BOT_SH, WORKFLOW):
            with self.subTest(os.path.basename(path)):
                self.assertNotIn(gone, source_of(path))


class AnInterfaceWithNoWrapperIsRefusedByName(unittest.TestCase):
    """The refusal, executed rather than read off the `raise`.

    A source read cannot say the raise is reachable, and "the wrapper is chosen
    from the bot's own import" is only worth anything if the unsupported case
    stops the launch instead of falling through to whatever `Main.elm` happens
    to be. `prepare_build_dir` is driven against a throwaway app directory --
    no `elm`, no compile, no network: it copies, patches `elm.json` and picks
    the wrapper, and the pick is the whole of what is under test.
    """

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="wrapper-test-")
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)
        # `throwaway` rather than `app`, and not a style choice:
        # `test_prerequisites.NoFileCarriesItsOwnHarness` refuses any test
        # module that names the built tree's own attributes, because a module
        # reaching for that tree can write into what the next class in the
        # process compiles. (Which is why this comment does not spell them
        # either: the guard reads the file, comments included, and is right
        # to -- a name in a comment is one paste away from being a name in
        # code.)
        # This directory is a `mkdtemp` of its own and nothing here touches
        # that tree -- the module imports no harness at all -- but the guard
        # cannot tell the two apart from the outside, and it should not have to
        # be taught to. Renaming this back is what makes that guard go red.
        self.throwaway = os.path.join(self.workdir, "app")
        os.makedirs(self.throwaway)
        with open(os.path.join(self.throwaway, "elm.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"type": "application", "elm-version": "0.19.1"}, handle)

    def write_bot(self, interface):
        with open(os.path.join(self.throwaway, "Bot.elm"), "w",
                  encoding="utf-8") as handle:
            handle.write(
                "module Bot exposing (botMain)\n\n"
                "import %s as InterfaceToHost\n" % interface)

    def prepare(self, into):
        return botlab_host.prepare_build_dir(
            self.throwaway, os.path.join(self.workdir, into))

    def test_an_unknown_interface_stops_the_launch_and_names_it(self):
        self.write_bot("BotLab.BotInterface_To_Host_1999_01_01")
        os.makedirs(os.path.join(self.workdir, "unknown"))
        with self.assertRaises(RuntimeError) as raised:
            self.prepare("unknown")
        message = str(raised.exception)
        self.assertIn("BotLab.BotInterface_To_Host_1999_01_01", message)
        self.assertIn(CURRENT_INTERFACE, message,
                      "the refusal has to say what the host does carry, or an "
                      "operator cannot tell a retired interface from a typo")

    def test_the_retired_interface_is_refused_like_any_other(self):
        # Named rather than left to the case above: this is the one an operator
        # is most likely to meet, by pointing the host at an old checkout.
        self.write_bot("BotLab.BotInterface_To_Host_2023_02_06")
        os.makedirs(os.path.join(self.workdir, "retired"))
        with self.assertRaises(RuntimeError) as raised:
            self.prepare("retired")
        self.assertIn("2023_02_06", str(raised.exception))

    def test_a_bot_with_no_import_at_all_is_refused_too(self):
        with open(os.path.join(self.throwaway, "Bot.elm"), "w",
                  encoding="utf-8") as handle:
            handle.write("module Bot exposing (botMain)\n")
        os.makedirs(os.path.join(self.workdir, "none"))
        with self.assertRaises(RuntimeError):
            self.prepare("none")

    def test_the_current_interface_gets_the_wrapper(self):
        # The control: without it every case above would pass on a
        # `prepare_build_dir` that refused everything.
        self.write_bot(CURRENT_INTERFACE)
        os.makedirs(os.path.join(self.workdir, "current"))
        build = self.prepare("current")
        self.assertEqual(
            source_of(os.path.join(build, "Main.elm")),
            source_of(botlab_host.MAIN_ELM_TEMPLATE))


class TheHostNoLongerCarriesTheRetiredInterface(unittest.TestCase):
    """What went with the app, asserted so a partial revert is visible.

    Each of these was reachable only when a bot on `2023_02_06` was running, and
    each is named rather than the removal being asserted as a diff: a half-
    restored input path -- the translation back without the interception, say --
    would compile and would do nothing, which is this repo's signature failure.
    """

    GONE = (
        # Input arrived inside the volatile-process request rather than as its
        # own task, so the host intercepted and translated it.
        "_effect_sequence_of_request",
        "_effect_sequence_as_input_items",
        "MOUSE_BUTTON_VK_CODES",
        # #332: that interface decoded only a flat SearchUIRootAddressResult,
        # so the host answered it synchronously on the request thread.
        "legacy_search_ui_root",
        "_search_ui_root_blocking",
    )

    def test_none_of_the_retired_paths_are_back(self):
        source = source_of(os.path.join(
            MACOS_HOST_DIR, "botlab_host", "botlab_host.py"))
        for name in self.GONE:
            with self.subTest(name):
                self.assertNotIn(
                    name, source,
                    "%s is back in the host. It was reachable only for a bot "
                    "on BotLab.BotInterface_To_Host_2023_02_06, which no app "
                    "imports -- see notes/retire-wingus.md before restoring "
                    "half of it" % name)

    def test_the_staged_search_is_what_the_host_answers(self):
        """The 2024 path, which the removal had to leave exactly as it was.

        `test_legacy_search_ui_root.py` carried this case beside the flag it was
        named for; the flag went and this half is worth keeping, because it is
        the answer every current bot's setup state machine decodes.
        """
        host = botlab_host.VolatileHost()
        # The search itself is stubbed: it needs a live client and the native
        # `memory_sample` binary, and what is under test is the shape of the
        # answer rather than the search. Left unstubbed it also writes a
        # failure line to stderr from a daemon thread, after the case has
        # passed, which reads like a test problem and is not one.
        host._find_ui_root = lambda process_id: 0x1234
        response = json.loads(host.handle_request(
            json.dumps({"SearchUIRootAddress": {"processId": 2796}})))
        self.assertIn("SearchUIRootAddressResponse", response)
        self.assertIn("stage", response["SearchUIRootAddressResponse"])

    def test_the_search_is_answered_without_waiting_for_it(self):
        """The property the blocking path did not have, and its whole point.

        The request thread answers with the search's *current stage* and
        returns; the search itself runs on a worker. Asserted by holding the
        search open and requiring an answer anyway -- a `_find_ui_root` call
        counter would be racy, since the worker is free to have run by the time
        the assertion is made, and it would also pass for a blocking answer.
        """
        host = botlab_host.VolatileHost()
        release = threading.Event()
        self.addCleanup(release.set)

        def held(process_id):
            release.wait(30)
            return 0x1234

        host._find_ui_root = held
        response = json.loads(host.handle_request(
            json.dumps({"SearchUIRootAddress": {"processId": 2796}})))
        self.assertIn(
            "SearchUIRootAddressInProgress",
            response["SearchUIRootAddressResponse"]["stage"],
            "handle_request waited for the UI root on the calling thread, "
            "which is what the retired interface's synchronous answer did")


if __name__ == "__main__":
    unittest.main()
