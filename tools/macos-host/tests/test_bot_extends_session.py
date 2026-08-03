"""Tests for the bot asking the host for time past the planned session end.

Every overrun in the mission runner's wind-down is expressed as "how far past
the planned end may this run" -- `homeStationTripSecondsPastSessionEnd` (420 s),
`homeStationRoutePreparationSecondsPastSessionEnd` (120 s),
`homeStationRestockGraceSeconds` (60 s),
`secondsPastSessionEndBeforeGivingUpOnDocking` (120 s) -- and **none of them
could ever be spent**, because `run_bot` stopped the run the instant the planned
end passed:

    if overrun_seconds > 0:
        print("# session duration elapsed ... -- stopping")
        break

Run 17 died on exactly that line, mid-trip to its home station, with its own
clock reading 420 s of headroom. Four constants, all reachable-looking, all in
time that could not happen -- this repo's signature bug, in the deadline
machinery itself.

**The deadline stays the host's to enforce.** What changes is that the bot may
now *ask*, and the host grants up to a cap. Three properties are what make
handing a bound to the thing being bounded safe, and each has a case below:

- **It is a lease, renewed every tick.** The host reads it out of the current
  tick's status text, so a bot that stops asking is stopped on the next tick,
  and one that has hung or crashed asks for nothing at all. Nothing latches.
- **It is capped by the host**, not trusted. `MAX_BOT_REQUESTED_OVERRUN_SECONDS`
  is above every allowance the mission runner can ask for and far below anything
  that would let a looping bot run on unnoticed.
- **It is announced.** A session quietly running past its end is precisely what
  an operator would not think to look for.

**The channel is the status text**, because `InterfaceToHost.ContinueSession`
offers exactly three fields -- `statusText`, `startTasks`,
`notifyWhenArrivedAtTime` -- and the first is the only one that can carry a fact
the protocol has no type for. Adding a type means changing vendored codecs on
both sides, the same closed-decoder problem that made #30's game log ride the UI
tree rather than extend `ReadFromWindowResult`. So the token has to be one that
cannot occur by accident in a field otherwise full of prose and mission names,
and **the two languages have to agree on it** -- which is what the first class
below pins, in #30's own pattern.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
import botlab_host  # noqa: E402


def bot_source():
    with open(BOT_ELM, encoding="utf-8") as source:
        return source.read()


def elm_int_constant(source, name):
    match = re.search(r"^%s =\n\s*(-?\d+)" % re.escape(name), source, re.M)
    assert match, "could not find %s in Bot.elm" % name
    return int(match.group(1))


def elm_string_constant(source, name):
    match = re.search(r'^%s =\n\s*"([^"]*)"' % re.escape(name), source, re.M)
    assert match, "could not find %s in Bot.elm" % name
    return match.group(1)


class TheTwoLanguagesAgreeOnTheToken(unittest.TestCase):
    """The host scans a free-prose field for this. If the two ever drift the bot
    asks and the host does not hear -- which reads exactly like a bot that never
    asked, and ends the session at the planned end as before."""

    def setUp(self):
        self.source = bot_source()

    def test_the_prefix_the_bot_writes_is_the_one_the_host_matches(self):
        prefix = elm_string_constant(self.source, "hostDirectivePrefix")
        self.assertTrue(
            botlab_host.BOT_DIRECTIVE_EXTEND_SESSION.pattern.startswith(
                re.escape(prefix).replace("\\ ", " ")),
            "host pattern %r does not start with the bot's prefix %r"
            % (botlab_host.BOT_DIRECTIVE_EXTEND_SESSION.pattern, prefix))

    def test_a_real_status_line_from_the_bot_parses(self):
        """Built the way `statusTextFromState` builds it, directive last."""
        prefix = elm_string_constant(self.source, "hostDirectivePrefix")
        status = "\n".join([
            "Mission: Technological Secrets (3 of 3) -- no instruction",
            "ship ok | Home station: 'Amarr VIII (Oris)' (drone bay last seen empty).",
            prefix + "extend-session 480",
        ])
        self.assertEqual(480.0, botlab_host.bot_requested_overrun_seconds(status))

    def test_the_token_cannot_be_produced_by_ordinary_prose(self):
        for innocent in [
            "Mission: The Score -- no instruction (next step: Dock)",
            "Home station: 'Amarr VIII (Oris) - Emperor Family Academy'.",
            "extend session 480",
            "@host",
            "@host extend-session",
            "the agent said host extend-session 480",
        ]:
            with self.subTest(innocent=innocent):
                self.assertEqual(
                    0.0, botlab_host.bot_requested_overrun_seconds(innocent))


class TheHostCapsWhatItGrants(unittest.TestCase):

    def test_nothing_asked_is_nothing_granted(self):
        self.assertEqual(0.0, botlab_host.bot_requested_overrun_seconds(""))
        self.assertEqual(0.0, botlab_host.bot_requested_overrun_seconds(None))

    def test_a_reasonable_ask_is_granted_whole(self):
        self.assertEqual(
            420.0,
            botlab_host.bot_requested_overrun_seconds("@host extend-session 420"))

    def test_an_absurd_ask_is_clamped(self):
        self.assertEqual(
            botlab_host.MAX_BOT_REQUESTED_OVERRUN_SECONDS,
            botlab_host.bot_requested_overrun_seconds("@host extend-session 99999"))

    def test_the_cap_covers_every_allowance_the_bot_can_ask_for(self):
        """Otherwise the cap silently truncates a legitimate wind-down, which is
        the same unreachable-time bug one level up."""
        source = bot_source()
        largest = (elm_int_constant(source, "homeStationTripSecondsPastSessionEnd")
                   + elm_int_constant(source, "homeStationRestockGraceSeconds"))
        self.assertLessEqual(
            largest, botlab_host.MAX_BOT_REQUESTED_OVERRUN_SECONDS)

    def test_the_cap_is_not_unbounded(self):
        self.assertLess(botlab_host.MAX_BOT_REQUESTED_OVERRUN_SECONDS, 3600)


class TheHostStillOwnsTheDeadline(unittest.TestCase):
    """Read out of the loop, because the properties are about where the call
    sits rather than what it returns."""

    def setUp(self):
        with open(os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py"),
                  encoding="utf-8") as source:
            self.source = source.read()

    def test_the_lease_is_read_from_this_tick_not_remembered(self):
        self.assertIn(
            'granted_seconds = bot_requested_overrun_seconds(cont.get("statusText"))',
            self.source)

    def test_the_run_still_stops_when_the_ask_runs_out(self):
        self.assertIn("if overrun_seconds > granted_seconds:", self.source)
        self.assertIn("break", self.source)

    def test_a_granted_extension_is_announced(self):
        self.assertIn("the bot asked for", self.source)
        self.assertIn("continuing", self.source)

    def test_the_old_unconditional_stop_is_gone(self):
        """`overrun_seconds > 0` as the stop condition is what made all four
        allowances unreachable."""
        self.assertNotIn("if overrun_seconds > 0:\n                print", self.source)


class TheBotOnlyAsksWhileItNeedsTo(unittest.TestCase):
    """Read out of `Bot.elm`. The value itself is asked of the same two
    functions the wind-down asks, so the number the host is told cannot drift
    from the number the bot is using."""

    def setUp(self):
        self.source = bot_source()

    def test_it_asks_the_wind_downs_own_functions_for_the_number(self):
        body = re.search(
            r"sessionOverrunSecondsNeeded context =.*?(?=\n\n\n)",
            self.source, re.S).group(0)
        self.assertIn("dockedWindDownDeadlineSeconds context", body)
        self.assertIn("windDownOverrunAllowanceSeconds context", body)

    def test_it_is_silent_outside_the_wind_down(self):
        body = re.search(
            r"hostDirectiveExtendSession context =.*?(?=\n\n\n)",
            self.source, re.S).group(0)
        self.assertIn("secondsBeforeSessionEndToWindDown < secondsRemaining", body)
        self.assertIn('""', body)

    def test_it_is_silent_when_nothing_is_needed(self):
        body = re.search(
            r"hostDirectiveExtendSession context =.*?(?=\n\n\n)",
            self.source, re.S).group(0)
        self.assertIn("needed <= 0", body)

    def test_it_is_silent_without_a_session_end(self):
        body = re.search(
            r"hostDirectiveExtendSession context =.*?(?=\n\n\n)",
            self.source, re.S).group(0)
        self.assertIn("Nothing ->", body)

    def test_the_directive_is_the_last_line_of_the_status_text(self):
        """The host prints the status text inline after the tick marker, so the
        first line has to stay the mission -- `stall_watch.py` and every log
        grep in this repo read it that way."""
        block = re.search(
            r"\[ \[ describePerformance \].*?String\.join \"\\n\"",
            self.source, re.S).group(0)
        self.assertLess(
            block.index("describeCurrentReading"),
            block.index("hostDirectiveExtendSession"))


if __name__ == "__main__":
    unittest.main()
