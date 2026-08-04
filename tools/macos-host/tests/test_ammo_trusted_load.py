"""The ammo swap trusts a load it dispatched, and what that trust rests on.

Issue #85. The swap used to finish by re-opening a weapon's menu and looking for
the charge to have gone from the list. Run 26 says what that cost and what it
bought:

- **183 of the 201 decision lines printed while the swap held the guns** are the
  re-opening branch -- 91% of the disarmed window spent proving a load;
- and it produced its answer on **one of seven swaps**, because a re-opened menu
  is only attributable to a weapon when the client draws it on the very next
  reading, which `menuOpenOnGunAtX` is the only thing that can tell.

What replaces it is not optimism, and this file is mostly about saying which
part is the evidence. `ammoSwapLoadIsTrusted` takes the absence of the client's
own refusal as the load having landed, and the two recorded runs are the control
pair for that inference:

    run 22   134 "cannot load or unload"   0 (satisfied)   every load refused
    run 26     0 "cannot load or unload"   2628 (satisfied)   none refused

So the arbiter speaks when a load fails and is silent when one lands. **The
trust is exactly as good as that sentence arriving**, which is why the refusal
veto is executed here rather than read, and why the dependency is asserted to be
written down in `loadRefusalFromGameLog` where someone editing #31 would find it.

The identity the menu read also carried is preserved rather than dropped: the
charge the swap asked for is recorded as the charge in the gun, flagged as
assumed on the status line, and overwritten by any menu read that disagrees.
Runs 17 and 18 are what dropping it looks like -- `loaded charge reads unknown`
on every ammo status line they have, and no next verdict forming.

The rule is executed through the shared `elm repl` harness rather than restated
in Python; everything that is about the *shape* of the source is read out of
`Bot.elm` through a whitespace-collapsing reader, so the next `elm-format` pass
cannot break it.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Quoted from run 22's own game log, where it appears 134 times.
RECORDED_REFUSAL = (
    "You cannot load or unload Focused Modulated Medium Energy Beam I "
    "while it is active.")

# The branch text run 26 printed 183 times, which this change removes. Kept
# here as the thing the source must no longer contain -- reintroducing the
# re-read is the regression, and it would otherwise look like an improvement.
RETIRED_VERIFICATION = "re-open the last one's menu to see whether it took"


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """The source with every run of whitespace as one space.

    #58 broke three source assertions by reformatting, and the fix there was
    this: assert on what the code says, not on how it is laid out.
    """
    return re.sub(r"\s+", " ", text)


def definition_body(source, name, indent="        "):
    """The right-hand side of a `let` binding, up to the next binding."""
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    end = re.search(r"\n\n" + indent + r"\S", rest)
    return rest[:end.start()] if end else rest


def doc_comment_for(source, name):
    """The `{-| ... -}` block immediately preceding a top-level declaration."""
    signature = re.search(r"^" + name + r" :", source, re.MULTILINE)
    if signature is None:
        raise AssertionError("no top-level declaration named " + name)
    before = source[:signature.start()]
    opened = before.rindex("{-|")
    return before[opened:]


def int_constant(source, name):
    match = re.search(r"^" + name + r" : Int\n" + name + r" =\n\s+(\d+)",
                      source, re.MULTILINE)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return int(match.group(1))


def trust_case(same_verdict=True, every_gun=True, dispatched=True,
               refusal=None, menu_contradicts=False):
    def flag(value):
        return "True" if value else "False"

    quoted = "Nothing" if refusal is None else 'Just "%s"' % refusal
    return (
        "ammoSwapLoadIsTrusted { verdictIsTheSameOneAsBefore = %s"
        ", everyGunVisited = %s, loadWasDispatched = %s"
        ", loadRefusedByClient = %s, menuContradictsTheLoad = %s }"
        % (flag(same_verdict), flag(every_gun), flag(dispatched), quoted,
           flag(menu_contradicts)))


class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-ammo-trusted-load-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_dispatched_load_the_client_did_not_refuse_is_trusted(self):
        # The ordinary case, and the whole point: this is the reading the swap
        # now finishes on instead of re-opening a menu for another eight.
        self.assertEqual(self.repl.evaluate([trust_case()]), [True])

    def test_the_client_s_own_refusal_vetoes_it(self):
        # #31, executed. Run 22 wrote this sentence 134 times when every load
        # was going into a running gun; if it stops vetoing, the swap starts
        # reporting a charge the gun does not have.
        answers = self.repl.evaluate([
            trust_case(refusal=RECORDED_REFUSAL),
            trust_case(refusal="You cannot load or unload 425mm AutoCannon II "
                               "while it is active."),
        ])
        self.assertEqual(
            answers, [False, False],
            "a load the client said it threw away is being trusted -- see "
            "loadRefusalFromGameLog for what that costs")

    def test_a_load_that_has_not_gone_out_is_not_trusted(self):
        # The trap this design has to avoid. `loadCascadeReachedTheMenu` is
        # true on the reading the cascade clicks the charge entry, so reading
        # it on that same reading would satisfy the verdict, idle the acting
        # path, and trust a click that was never dispatched.
        self.assertEqual(self.repl.evaluate([trust_case(dispatched=False)]),
                         [False])

    def test_a_gun_still_waiting_for_its_turn_is_not_trusted(self):
        # On a multi-weapon row the first gun's menu must not end the walk.
        self.assertEqual(self.repl.evaluate([trust_case(every_gun=False)]),
                         [False])

    def test_a_verdict_that_has_just_changed_has_dispatched_nothing(self):
        self.assertEqual(self.repl.evaluate([trust_case(same_verdict=False)]),
                         [False])

    def test_a_menu_read_that_disagrees_beats_the_assumption(self):
        # The read is the client speaking and it costs nothing when it happens
        # to arrive, so it wins in both directions.
        self.assertEqual(
            self.repl.evaluate([trust_case(menu_contradicts=True)]), [False])

    def test_every_input_can_refuse_on_its_own(self):
        # Each of the five is a distinct way this can be wrong; a rule that
        # only consulted some of them would pass the cases above by accident.
        answers = self.repl.evaluate([
            trust_case(same_verdict=False), trust_case(every_gun=False),
            trust_case(dispatched=False), trust_case(refusal=RECORDED_REFUSAL),
            trust_case(menu_contradicts=True),
        ])
        self.assertEqual(answers, [False] * 5)


class TheAssumptionIsWiredWhereItSaysItIs(unittest.TestCase):
    def setUp(self):
        self.source = bot_elm()
        self.collapsed = collapsed(self.source)

    def test_the_dispatch_is_read_from_the_previous_reading(self):
        # Reading it from this reading is the failure the rule's own doc
        # comment describes: the verdict would be satisfied before the click
        # went out. So the call site must pass `memoryBefore`'s copy.
        self.assertIn(
            "loadWasDispatched = memoryBefore.loadCascadeReachedTheMenu",
            self.collapsed,
            "the trust is reading this reading's cascade state, so the swap "
            "can finish before it has clicked the charge entry")

    def test_the_verdict_consults_the_trust(self):
        body = collapsed(definition_body(self.source, "verdictSatisfied"))
        self.assertIn("loadIsTrusted", body)

    def test_a_refusal_unsatisfies_a_verdict_it_arrives_after(self):
        # The refusal can be one reading later than the click, which is one
        # reading after the trust fired. Without this clause the latch would
        # carry a load the client had already disowned.
        body = collapsed(definition_body(self.source, "verdictSatisfied"))
        self.assertIn("loadRefusedByClient /= Nothing", body)
        self.assertLess(
            body.index("loadRefusedByClient /= Nothing"),
            body.index("loadIsTrusted"),
            "the refusal has to be asked before the trust, or a verdict "
            "trusted on an earlier reading survives the client disowning it")

    def test_the_re_read_after_the_load_is_gone(self):
        self.assertNotIn(
            RETIRED_VERIFICATION, self.source,
            "the branch that re-opened a menu to confirm a load is back; that "
            "is 91% of run 26's disarmed window for an answer it got once in "
            "seven swaps")

    def test_the_branch_that_replaced_it_still_drives_the_cascade(self):
        # It is not a wait and not a check: without it the cascade opened on
        # the last gun never reaches the reading it clicks the charge entry.
        self.assertIn("(loadTheWantedCharge gunCommandedLast)", self.collapsed)

    def test_the_cascade_is_driven_at_the_gun_it_last_right_clicked(self):
        body = collapsed(definition_body(self.source, "gunCommandedLast",
                                         indent="        "))
        self.assertIn("ammoSwap.gunsCommandedThisVerdictAtX |> List.head", body)


class TheLoadedChargeIdentityIsKept(unittest.TestCase):
    """Runs 17 and 18 are what losing it looks like, and it is not cheap.

    `loaded charge reads unknown` is the state that stops the next verdict
    forming, so "trust the load" had to mean recording the charge rather than
    forgetting it.
    """

    def setUp(self):
        self.source = bot_elm()
        self.collapsed = collapsed(self.source)

    def test_the_charge_the_swap_asked_for_is_what_gets_recorded(self):
        body = collapsed(definition_body(self.source, "chargeLoadedOrAssumed"))
        self.assertIn("if loadIsTrusted then rangeVerdict", body)
        self.assertIn("chargeLoaded = chargeLoadedOrAssumed", self.collapsed)

    def test_a_menu_read_still_outranks_the_assumption(self):
        body = collapsed(definition_body(self.source, "chargeLoadedIsAssumed"))
        self.assertLess(
            body.index("menuWasRead"), body.index("loadIsTrusted"),
            "the assumption is being preferred over a read of the client's "
            "own menu, which is the better evidence and is free")

    def test_the_operator_can_tell_the_two_answers_apart(self):
        # A status line that reported an assumed charge identically to a read
        # one would make the next investigation impossible.
        self.assertIn("ammoSwap.chargeLoadedIsAssumed", self.collapsed)
        self.assertIn("assumed from the load", self.collapsed)

    def test_the_optimal_range_is_forgotten_when_the_charge_changes(self):
        # This is how the second of the two optimal ranges is ever seen, and
        # therefore how run 26 reached a 44000 m crossover from the midpoint
        # instead of staying on the 67000 m bootstrap. An assumed change makes
        # the number as stale as a read one does.
        body = collapsed(definition_body(self.source, "optimalRangeAfterTheLoad"))
        self.assertIn("if chargeLoadedOrAssumed == chargeLoaded", body)
        self.assertIn("freshOptimalRange", body)
        self.assertIn("optimalRangeInMeters = optimalRangeAfterTheLoad",
                      self.collapsed)

    def test_a_context_menu_is_only_a_weapon_s_if_it_offers_the_charge(self):
        # What makes `loadCascadeReachedTheMenu` safe without `menuOpenOnGunAtX`:
        # nothing else the client opens lists a charge by name.
        body = collapsed(definition_body(self.source,
                                         "loadCascadeReachedTheMenu"))
        self.assertIn("everyGunVisited && wantedChargeIsOfferedByAnOpenMenu",
                      body)


class TheDependencyOnTheRefusalIsWrittenDown(unittest.TestCase):
    """#31 can be edited by someone who has never read #85.

    A note in a pull request is not where that person is looking, so the
    dependency is asserted to be in the matcher's own doc comment.
    """

    def setUp(self):
        self.source = bot_elm()

    def test_the_matcher_says_what_now_rests_on_it(self):
        doc = collapsed(doc_comment_for(self.source, "loadRefusalFromGameLog"))
        self.assertIn(
            "ammoSwapLoadIsTrusted", doc,
            "loadRefusalFromGameLog no longer names the rule that depends on "
            "it, so removing this matcher would silently take the ammo swap's "
            "account of what is in the gun with it")
        self.assertIn("#85", doc)

    def test_the_rule_says_what_it_rests_on(self):
        doc = collapsed(doc_comment_for(self.source, "ammoSwapLoadIsTrusted"))
        self.assertIn("loadRefusalFromGameLog", doc)
        self.assertIn("#31", doc)


class TheBoundsAreUntouched(unittest.TestCase):
    """The change shortens the window by removing work, not by loosening a bound.

    #38's deadline and the settle are both measured numbers, and the guns-off
    window dropping is supposed to be the *consequence* of the swap finishing
    sooner.
    """

    def setUp(self):
        self.source = bot_elm()

    def test_the_guns_off_deadline_is_still_twenty(self):
        self.assertEqual(int_constant(self.source,
                                      "ammoSwapSilencedGiveUpTicks"), 20)

    def test_the_settle_is_still_three(self):
        # Measured across run 26's seven swaps before touching it: on four the
        # client's own `isInActiveState` confirmation ended the settle at one
        # reading or none, and on the other three it never confirmed at all
        # within seven readings, so the count is the only thing that ends the
        # wait there. Nothing in the corpus shows a load accepted earlier than
        # this, and run 22's 134 refusals are what loading too early costs.
        self.assertEqual(int_constant(self.source,
                                      "ammoSwapSilenceSettleTicks"), 3)


class AgainstTheRecordedRuns(unittest.TestCase):
    """The measurement the change is made on, asserted rather than remembered."""

    def lines(self, name):
        [(_, path)] = recorded_runs(name)
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()

    def test_run_22_is_the_control_where_every_load_was_refused(self):
        lines = self.lines("22")
        refusals = [line for line in lines if "cannot load or unload" in line]
        satisfied = [line for line in lines if "(satisfied)" in line]
        self.assertGreater(
            len(refusals), 100,
            "run 22 is the run where the client refused every load; without "
            "those lines it is not evidence that the refusal fires")
        self.assertEqual(
            satisfied, [],
            "run 22 completed a swap, so it is no longer the control")

    def test_run_26_is_the_run_where_none_was_refused_and_loads_landed(self):
        lines = self.lines("26")
        refusals = [line for line in lines if "cannot load or unload" in line]
        satisfied = [line for line in lines if "(satisfied)" in line]
        self.assertEqual(
            refusals, [],
            "run 26 recorded a refusal after all, so 'a load that does not "
            "land is not silent' is being read off the wrong run")
        self.assertGreater(len(satisfied), 0)

    def test_the_verification_was_most_of_run_26_s_disarmed_window(self):
        # Every decision line printed while the swap held the guns carries one
        # of the two hold clauses, so this counts the window without having to
        # reconstruct readings.
        lines = self.lines("26")
        held = [line for line in lines
                if line.startswith("+ ")
                and (re.search(r"Guns off for \d+ of", line)
                     or "readings of this attempt spent" in line)]
        verifying = [line for line in held if RETIRED_VERIFICATION in line]
        self.assertGreater(len(held), 100, "run 26 has no disarmed window to "
                                           "measure")
        self.assertGreater(
            len(verifying) * 10, len(held) * 8,
            "the re-read was under 80%% of run 26's disarmed window (%d of "
            "%d), so the measurement #85 is argued from does not hold and the "
            "trade should be re-derived" % (len(verifying), len(held)))


if __name__ == "__main__":
    unittest.main()
