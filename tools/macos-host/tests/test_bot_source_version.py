"""Tests for the version stamp the host prints and the console shows.

Issue #117: the console said neither which bot it was driving nor what code that
bot was built from, and establishing what a given run had executed took reading
git ancestry and grepping the compiled `bot.js` for string literals -- a method
that produced a confident false negative before it was caught.

**A bare `git rev-parse HEAD` is the wrong answer, and it is wrong in the
direction that looks authoritative**, which is what most of these cases are
about. Two facts have to travel with the commit, and each has a recorded run
behind it:

  - The host compiles the *working tree*. `prepare_build_dir` copies `bot_dir`
    as it stands and `elm make` builds the copy, and the mission runner is
    edited while runs are in flight, so a clean-looking SHA beside modified
    sources describes something that never ran.
  - The commit may exist nowhere but this machine. Run 29 flew `776a202`, a
    local revert that was never pushed; a reader handed that SHA alone cannot
    resolve it against anything.

And the third case is that there may be no answer at all: `fetch_bot_source`
takes a plain directory as readily as a GitHub URL, so a source that is not a
git checkout must degrade to a stated "unknown" -- never a crash, never a blank,
and never a value nobody can look up. `loadRefusalFromGameLog`'s register in
`Bot.elm`, applied to a version string: absent evidence is not a finding.

The git cases are *executed* rather than described. Each builds a real
throwaway checkout shaped like this repo -- the bot's own directory, other files
beside it -- and runs the real `git`, because a Python restatement of "is this
tree dirty" would only ever test the restatement. Nothing here reads this
repository, `~/eve-bot-logs`, a live client or a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
sys.path.insert(0, MACOS_HOST_DIR)

import botlab_host  # noqa: E402
import web_console  # noqa: E402

HOST_SOURCE = os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py")
CONSOLE_PAGE = os.path.join(MACOS_HOST_DIR, "web_console.html")


def collapse(path):
    """Whitespace-collapsed source, so reformatting cannot break an assertion."""
    with open(path) as f:
        return re.sub(r"\s+", " ", f.read())


def git(repo, *args):
    """Run git in `repo` for the fixtures, failing loudly if it will not.

    Identity is supplied per command rather than written into the throwaway
    repo, so these cases neither read nor need the machine's git config.
    """
    done = subprocess.run(
        ["git", "-C", repo, "-c", "user.email=test@example.invalid",
         "-c", "user.name=test", *args],
        capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


class Checkout:
    """A throwaway checkout shaped like this one.

    The bot lives in its own directory under the repository root and other
    files sit beside it, because "is the thing that was compiled dirty" and "is
    anything in this repository dirty" are different questions and the stamp
    answers the first.
    """

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="bot-source-version-")
        self.bot_dir = os.path.join(
            self.root, "implement", "applications", "eve-online",
            "eve-online-mission-runner")
        self.write(os.path.join(self.bot_dir, "Bot.elm"), "module Bot exposing (..)\n")
        self.write(os.path.join(self.root, "tools", "macos-host", "stall_watch.py"), "# host\n")
        git(self.root, "init", "-q", "-b", "main")
        self.commit("the bot as it was")

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def commit(self, message):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def publish(self):
        """Make HEAD reachable from a remote-tracking ref, as a push would."""
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")

    def add_remote(self, url, name="origin"):
        """Register a remote, the way `remote get-url` needs one registered.

        `publish()` only fakes the remote-tracking ref a push would leave
        behind; it adds no actual remote, and `git remote get-url` has nothing
        to answer without one. `git remote add` never contacts the URL, so
        this is as local as everything else the fixture does.
        """
        git(self.root, "remote", "add", name, url)

    def set_remote_head(self, branch, name="origin"):
        """Point `<name>/HEAD` at `branch`, the way `git clone` does.

        Needs `refs/remotes/<name>/<branch>` to already exist -- ordinarily
        from `publish()` -- since `symbolic-ref` does not create the ref it
        points at.
        """
        git(self.root, "symbolic-ref", f"refs/remotes/{name}/HEAD",
           f"refs/remotes/{name}/{branch}")

    def short_head(self):
        return git(self.root, "rev-parse", "--short", "HEAD").strip()

    def remove(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Stamp(unittest.TestCase):
    def setUp(self):
        self.checkout = Checkout()
        self.addCleanup(self.checkout.remove)

    def version(self):
        return botlab_host.bot_source_version(self.checkout.bot_dir)

    def test_clean_tree_on_a_remote_tracking_branch(self):
        self.checkout.publish()
        self.assertEqual(
            self.version(),
            f"{self.checkout.short_head()} (clean, on a remote-tracking branch)")

    def test_an_edited_source_file_is_not_the_commit(self):
        # The case the whole stamp exists for: HEAD is pushed and clean-looking,
        # and what elm make will compile is not what HEAD says.
        self.checkout.publish()
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"),
                            "module Bot exposing (..)\n-- edited mid-run\n")
        self.assertEqual(
            self.version(),
            f"{self.checkout.short_head()} (DIRTY, on a remote-tracking branch)")

    def test_an_untracked_file_beside_the_bot_is_dirty_too(self):
        # prepare_build_dir copies the directory, so an untracked file travels
        # into the build exactly as an edited one does.
        self.checkout.publish()
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Scratch.elm"), "x\n")
        self.assertIn("DIRTY", self.version())

    def test_an_edit_elsewhere_in_the_checkout_is_not_this_bot_dirty(self):
        # The scoping decision, stated as a case: the host and its tests live in
        # the same checkout and are edited constantly, and none of that changes
        # what this bot compiled.
        self.checkout.publish()
        self.checkout.write(
            os.path.join(self.checkout.root, "tools", "macos-host", "stall_watch.py"),
            "# host, edited\n")
        self.assertEqual(
            self.version(),
            f"{self.checkout.short_head()} (clean, on a remote-tracking branch)")

    def test_a_commit_that_exists_only_here_says_so(self):
        # Run 29's 776a202: a local revert that was never pushed. The stamp must
        # not imply a commit a reader can go and resolve.
        self.checkout.publish()
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"),
                            "module Bot exposing (..)\n-- reverted locally\n")
        self.checkout.commit("a revert that never left this machine")
        self.assertEqual(self.version(),
                         f"{self.checkout.short_head()} (clean, LOCAL-ONLY)")

    def test_local_only_and_dirty_at_once(self):
        self.checkout.publish()
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"), "committed\n")
        self.checkout.commit("a commit that never left this machine")
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"), "and then edited\n")
        self.assertEqual(self.version(),
                         f"{self.checkout.short_head()} (DIRTY, LOCAL-ONLY)")

    def test_a_later_commit_does_not_make_an_older_one_local_only(self):
        # Reachability, not equality: a published commit stays published when the
        # remote-tracking ref has moved past it.
        self.checkout.publish()
        first = self.checkout.short_head()
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"), "next\n")
        self.checkout.commit("next")
        self.checkout.publish()
        git(self.checkout.root, "checkout", "-q", first)
        self.assertEqual(self.version(), f"{first} (clean, on a remote-tracking branch)")


class NoAnswerAvailable(unittest.TestCase):
    """Every question that cannot be answered says so, in place.

    Each of these would otherwise take the reassuring default -- clean, pushed,
    or a commit-shaped string -- which is the failure the stamp exists to
    prevent, one level down.
    """

    def test_a_source_that_is_not_a_checkout(self):
        plain = tempfile.mkdtemp(prefix="not-a-checkout-")
        self.addCleanup(shutil.rmtree, plain, True)
        self.assertEqual(botlab_host.bot_source_version(plain),
                         "unknown (not a git checkout)")

    def test_git_that_cannot_be_started(self):
        self.assertEqual(self._with_subprocess_raising(FileNotFoundError("no git")),
                         "unknown (git could not be run)")

    def test_git_that_runs_past_its_timeout(self):
        # A hung git holds the launch, which is why every call is bounded. The
        # bound is what makes this reachable rather than a hang.
        expired = subprocess.TimeoutExpired(cmd="git", timeout=1)
        self.assertEqual(self._with_subprocess_raising(expired),
                         "unknown (git could not be run)")

    def test_every_git_call_carries_a_timeout(self):
        calls = []
        real = botlab_host.subprocess.run

        def watched(*args, **kwargs):
            calls.append(kwargs.get("timeout"))
            return real(*args, **kwargs)

        checkout = Checkout()
        self.addCleanup(checkout.remove)
        botlab_host.subprocess.run = watched
        try:
            botlab_host.bot_source_version(checkout.bot_dir)
        finally:
            botlab_host.subprocess.run = real
        self.assertTrue(calls, "no git call was made at all")
        for timeout in calls:
            self.assertEqual(timeout, botlab_host.BOT_VERSION_GIT_TIMEOUT_SECONDS)

    def test_dirtiness_that_cannot_be_established_is_not_clean(self):
        checkout = Checkout()
        self.addCleanup(checkout.remove)
        checkout.publish()
        stamp = self._with_git_refusing(checkout.bot_dir, "status")
        self.assertEqual(
            stamp, f"{checkout.short_head()} (dirtiness unknown, on a remote-tracking branch)")

    def test_reachability_that_cannot_be_established_is_not_pushed(self):
        checkout = Checkout()
        self.addCleanup(checkout.remove)
        checkout.publish()
        stamp = self._with_git_refusing(checkout.bot_dir, "branch")
        self.assertEqual(
            stamp, f"{checkout.short_head()} (clean, remote reachability unknown)")

    def test_an_unexpected_failure_still_produces_a_stamp(self):
        # Whatever else goes wrong, the launch proceeds: a bot that will not
        # start because its version could not be computed is a worse outcome
        # than a bot that starts without one.
        real = botlab_host._git

        def exploding(*args, **kwargs):
            raise RuntimeError("something nobody predicted")

        botlab_host._git = exploding
        try:
            stamp = botlab_host.bot_source_version("/nowhere")
        finally:
            botlab_host._git = real
        self.assertTrue(stamp.startswith("unknown ("), stamp)
        self.assertIn("something nobody predicted", stamp)

    def _with_subprocess_raising(self, error):
        real = botlab_host.subprocess.run

        def refusing(*args, **kwargs):
            raise error

        botlab_host.subprocess.run = refusing
        try:
            return botlab_host.bot_source_version(HERE)
        finally:
            botlab_host.subprocess.run = real

    def _with_git_refusing(self, bot_dir, subcommand):
        """The stamp with one git subcommand answering as it does when it fails."""
        real = botlab_host._git

        def selective(cwd, *args):
            if args and args[0] == subcommand:
                return None
            return real(cwd, *args)

        botlab_host._git = selective
        try:
            return botlab_host.bot_source_version(bot_dir)
        finally:
            botlab_host._git = real


class Links(unittest.TestCase):
    """GitHub links for the commit the stamp names -- issue #317.

    A link is a claim that something is there to look at, so it has to
    respect exactly the same distinctions the stamp itself does: linkable
    only on `"on a remote-tracking branch"`, never on LOCAL-ONLY or unknown
    reachability, and never by guessing the remote -- the GitHub-URL source
    mode can point at a different fork than `smerwin/bots`.
    """

    def setUp(self):
        self.checkout = Checkout()
        self.addCleanup(self.checkout.remove)

    def links(self):
        return botlab_host.bot_source_links(self.checkout.bot_dir)

    # -- the table from the issue, row by row -------------------------------

    def test_clean_on_a_remote_tracking_branch_links(self):
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        links = self.links()
        self.assertNotIn("reason", links)
        self.assertEqual(links["commit"], self.checkout.short_head())
        self.assertFalse(links["dirty"])

    def test_dirty_on_a_remote_tracking_branch_links_but_says_so(self):
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"),
                            "module Bot exposing (..)\n-- edited mid-run\n")
        links = self.links()
        self.assertNotIn("reason", links)
        self.assertTrue(links["dirty"])
        self.assertIn("code", links)  # linked -- see the doc comment on why

    def test_local_only_does_not_link(self):
        # Run 29's 776a202: a local revert that was never pushed. A link would
        # 404.
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.write(os.path.join(self.checkout.bot_dir, "Bot.elm"),
                            "module Bot exposing (..)\n-- reverted locally\n")
        self.checkout.commit("a revert that never left this machine")
        links = self.links()
        self.assertEqual(links, {"reason": "LOCAL-ONLY"})

    def test_remote_reachability_unknown_does_not_link(self):
        # A fetch that has not happened must not be treated as "reachable",
        # same rule as the printed stamp.
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        real = botlab_host._git

        def selective(cwd, *args):
            if args and args[0] == "branch":
                return None
            return real(cwd, *args)

        botlab_host._git = selective
        try:
            links = self.links()
        finally:
            botlab_host._git = real
        self.assertEqual(links, {"reason": "remote reachability unknown"})

    def test_not_a_git_checkout_has_nothing_to_link(self):
        plain = tempfile.mkdtemp(prefix="not-a-checkout-")
        self.addCleanup(shutil.rmtree, plain, True)
        self.assertEqual(botlab_host.bot_source_links(plain),
                         {"reason": "not a git checkout"})

    def test_git_that_could_not_be_run_has_nothing_to_link(self):
        real = botlab_host.subprocess.run

        def refusing(*args, **kwargs):
            raise FileNotFoundError("no git")

        botlab_host.subprocess.run = refusing
        try:
            links = botlab_host.bot_source_links(HERE)
        finally:
            botlab_host.subprocess.run = real
        self.assertEqual(links, {"reason": "git could not be run"})

    def test_an_unexpected_failure_still_produces_an_answer(self):
        real = botlab_host._version_facts

        def exploding(*args, **kwargs):
            raise RuntimeError("something nobody predicted")

        botlab_host._version_facts = exploding
        try:
            links = botlab_host.bot_source_links("/nowhere")
        finally:
            botlab_host._version_facts = real
        self.assertIn("something nobody predicted", links["reason"])

    # -- remote URL parsing, both GitHub forms -------------------------------

    def test_https_remote_forms_parse(self):
        parse = botlab_host._parse_github_remote_url
        self.assertEqual(parse("https://github.com/smerwin/bots.git"), ("smerwin", "bots"))
        self.assertEqual(parse("https://github.com/smerwin/bots"), ("smerwin", "bots"))
        self.assertEqual(parse("https://github.com/smerwin/bots/"), ("smerwin", "bots"))

    def test_ssh_remote_forms_parse(self):
        parse = botlab_host._parse_github_remote_url
        self.assertEqual(parse("git@github.com:smerwin/bots.git"), ("smerwin", "bots"))
        self.assertEqual(parse("git@github.com:smerwin/bots"), ("smerwin", "bots"))
        self.assertEqual(parse("ssh://git@github.com/smerwin/bots.git"), ("smerwin", "bots"))

    def test_a_non_github_remote_does_not_parse(self):
        self.assertIsNone(botlab_host._parse_github_remote_url(
            "https://gitlab.com/smerwin/bots.git"))
        self.assertIsNone(botlab_host._parse_github_remote_url(""))
        self.assertIsNone(botlab_host._parse_github_remote_url(None))

    def test_a_non_github_remote_does_not_link(self):
        self.checkout.add_remote("https://gitlab.com/smerwin/bots.git")
        self.checkout.publish()
        links = self.links()
        self.assertEqual(links, {"reason": "remote 'origin' is not on github.com"})

    # -- the subpath, scoped to the bot rather than the repo root -----------

    def test_the_subpath_is_derived_and_scopes_the_code_link(self):
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        links = self.links()
        self.assertEqual(
            links["code"],
            f"https://github.com/smerwin/bots/tree/{links['commit']}/"
            "implement/applications/eve-online/eve-online-mission-runner")

    def test_the_blame_link_names_bot_elm_under_the_subpath(self):
        # There is no directory blame view on GitHub, so a file has to be
        # chosen -- Bot.elm is the one an operator reading a decision ladder
        # wants.
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        links = self.links()
        self.assertEqual(
            links["blame"],
            f"https://github.com/smerwin/bots/blame/{links['commit']}/"
            "implement/applications/eve-online/eve-online-mission-runner/Bot.elm")

    def test_a_repo_rooted_bot_links_with_no_trailing_slash(self):
        # If the bot directory ever were the repository root, `show-prefix`
        # answers the empty string -- the code link must not end in `/tree/<sha>/`.
        root_checkout = Checkout.__new__(Checkout)
        root_checkout.root = tempfile.mkdtemp(prefix="bot-source-version-root-")
        root_checkout.bot_dir = root_checkout.root
        root_checkout.write(os.path.join(root_checkout.bot_dir, "Bot.elm"),
                            "module Bot exposing (..)\n")
        self.addCleanup(root_checkout.remove)
        git(root_checkout.root, "init", "-q", "-b", "main")
        root_checkout.commit("root-level bot")
        root_checkout.add_remote("https://github.com/smerwin/bots.git")
        root_checkout.publish()
        links = botlab_host.bot_source_links(root_checkout.bot_dir)
        self.assertEqual(links["code"], f"https://github.com/smerwin/bots/tree/{links['commit']}")
        self.assertEqual(links["blame"],
                         f"https://github.com/smerwin/bots/blame/{links['commit']}/Bot.elm")

    # -- the two diff views --------------------------------------------------

    def test_the_commit_diff_names_the_commit_itself(self):
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        links = self.links()
        self.assertEqual(links["commitDiff"],
                         f"https://github.com/smerwin/bots/commit/{links['commit']}")

    def test_the_compare_diff_uses_the_remotes_default_branch_when_set(self):
        # `git clone` sets `refs/remotes/<remote>/HEAD`; read locally, no fetch.
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        self.checkout.set_remote_head("main")
        links = self.links()
        self.assertEqual(links["compareBranch"], "main")
        self.assertEqual(
            links["compareDiff"],
            f"https://github.com/smerwin/bots/compare/{links['commit']}...main")

    def test_the_compare_diff_falls_back_to_main_when_the_default_is_unset(self):
        # An older checkout, or a remote added by hand, has no
        # `refs/remotes/<remote>/HEAD` at all -- the compare link must still
        # have something to compare against.
        self.checkout.add_remote("https://github.com/smerwin/bots.git")
        self.checkout.publish()
        links = self.links()
        self.assertEqual(links["compareBranch"], "main")


class Launch(unittest.TestCase):
    """The stamp reaches the log and the console, and names the right thing."""

    def setUp(self):
        self.source = collapse(HOST_SOURCE)

    def test_the_version_is_computed_from_the_bot_source(self):
        # Not from the host's own location: the two differ under a GitHub-URL
        # source, and it is the bot's code being stamped.
        self.assertIn("bot_version = bot_source_version(bot_dir)", self.source)

    def test_the_app_name_is_the_bot_directory_leaf(self):
        # `eve-online-mission-runner` against `eve-online-saxrat` -- what an
        # operator with two consoles open actually needs.
        self.assertIn("bot_app_name = os.path.basename(os.path.normpath(bot_dir))",
                      self.source)

    def test_the_version_is_printed_beside_the_source_path(self):
        # The log is where "which code did this run fly" gets asked afterwards,
        # and it outlives every console.
        source_line = self.source.index('print(f"# bot source: {bot_dir}"')
        version_line = self.source.index('print(f"# bot version: {bot_version}"')
        self.assertLess(source_line, version_line)
        self.assertLess(version_line - source_line, 400,
                        "the version print has drifted away from the source print")

    def test_the_console_is_told_all_three(self):
        constructor = self.source[self.source.index("web_console.ConsoleState("):]
        constructor = constructor[:constructor.index(")")]
        self.assertIn("app_name=bot_app_name", constructor)
        self.assertIn("bot_source=bot_dir", constructor)
        self.assertIn("version=bot_version", constructor)

    def test_the_links_are_computed_from_the_bot_source(self):
        # Read once, beside the stamp itself, rather than a handler re-deriving
        # them later from the printed version string.
        self.assertIn("bot_links = bot_source_links(bot_dir)", self.source)

    def test_the_console_is_told_the_links_too(self):
        constructor = self.source[self.source.index("web_console.ConsoleState("):]
        constructor = constructor[:constructor.index(")")]
        self.assertIn("links=bot_links", constructor)


class Console(unittest.TestCase):
    def test_the_snapshot_carries_the_identity(self):
        state = web_console.ConsoleState(
            settings_text="", app_name="eve-online-mission-runner",
            bot_source="/Users/x/bots/implement/applications/eve-online/eve-online-mission-runner",
            version="1b7c731 (DIRTY, LOCAL-ONLY)")
        snapshot = state.snapshot()
        self.assertEqual(snapshot["appName"], "eve-online-mission-runner")
        self.assertEqual(snapshot["version"], "1b7c731 (DIRTY, LOCAL-ONLY)")
        self.assertTrue(snapshot["botSource"].endswith("eve-online-mission-runner"))

    def test_a_host_that_says_nothing_still_serves_a_console(self):
        # BotLab.exe is not the only caller shape: a ConsoleState built without
        # the identity must not fail the page it feeds.
        snapshot = web_console.ConsoleState().snapshot()
        self.assertEqual(snapshot["appName"], "")
        self.assertEqual(snapshot["version"], "")
        self.assertEqual(snapshot["botSource"], "")

    def test_the_page_shows_all_three_and_titles_the_tab(self):
        page = collapse(CONSOLE_PAGE)
        for element in ('id="app"', 'id="version"', 'id="source"'):
            self.assertIn(element, page)
        for field in ("s.appName", "s.version", "s.botSource"):
            self.assertIn(field, page)
        self.assertIn("document.title", page)

    def test_the_page_says_unknown_rather_than_showing_a_blank(self):
        page = collapse(CONSOLE_PAGE)
        self.assertIn("version unknown", page)
        self.assertIn("source unknown", page)

    def test_the_snapshot_carries_the_links(self):
        links = {"commit": "abc1234", "dirty": False,
                 "code": "https://github.com/smerwin/bots/tree/abc1234/implement/x",
                 "blame": "https://github.com/smerwin/bots/blame/abc1234/implement/x/Bot.elm",
                 "commitDiff": "https://github.com/smerwin/bots/commit/abc1234",
                 "compareDiff": "https://github.com/smerwin/bots/compare/abc1234...main",
                 "compareBranch": "main"}
        state = web_console.ConsoleState(version="abc1234 (clean, on a remote-tracking branch)",
                                         links=links)
        self.assertEqual(state.snapshot()["links"], links)

    def test_a_host_that_says_nothing_still_serves_a_console_with_no_links(self):
        snapshot = web_console.ConsoleState().snapshot()
        self.assertEqual(snapshot["links"], {})

    def test_a_no_link_reason_is_carried_through_unchanged(self):
        state = web_console.ConsoleState(
            version="a1b2c3d (clean, LOCAL-ONLY)", links={"reason": "LOCAL-ONLY"})
        self.assertEqual(state.snapshot()["links"], {"reason": "LOCAL-ONLY"})

    def test_the_page_renders_the_commit_as_a_link(self):
        page = collapse(CONSOLE_PAGE)
        self.assertIn('id="links"', page)
        self.assertIn("s.links", page)
        self.assertIn("links.code", page)
        self.assertIn("links.blame", page)
        self.assertIn("links.commitDiff", page)
        self.assertIn("links.compareDiff", page)
        self.assertIn("a.href", page)


if __name__ == "__main__":
    unittest.main()
