"""Tests for the wingman actually shooting what the fleet commander calls.

The bug these pin: a `Target` broadcast's banner **does not clear when the
target is locked**. It stays up for the rest of the call. The target arm of
`actOnFleetBroadcast` answered `Just (lock it)` on every reading while the
banner was up, and because that arm sits above `dronesAssistTheCommander` and
above the combat arm in `wingmanDecisionRootInSpace` -- where the first arm to
answer `Just` ends the reading -- the bot could never reach its drones or its
guns while a target was called.

So it locked what it was told to, correctly, on every reading, and never shot
it. Locking read as working and engaging read as broken, which is exactly how
it was reported from the field.

Three things had to change and each has cases here:

**The broadcast arm has to stand down once the lock exists**, otherwise
nothing below it is reachable. `bringCalledTargetUnderFire` answers `Nothing`
the moment the called target is locked.

**Something has to fire.** Before `fireOnActiveTarget`, the only thing in this
bot that ever activated a weapon was `fightUsingDronesAndModules`, reachable
only through `fightRatsIfShipIsPointed` -- which answers `Nothing` unless a rat
has pointed this ship. A target the commander called is not pointing anybody.

**The fallback must not undo the drones.** `fightPointedRatsOrReturnDrones`
recalled drones whenever the ship was not pointed, which with a called target
locked would have fought `dronesAssistTheCommander` on every reading.

## #389: the arm stood down against the wrong instrument, and the guns were
## billed for readings nobody spent

Live on all four pilots. Two defects, and each has its own class here.

**The recognition.** `bringCalledTargetUnderFire` asked `lockedTargetNamed`,
which matches the broadcast's name against the *target bar's* rendering. #303
read a live bar with a rat locked and got `['Tower Sentry', 'Sansha I', '20
km']` -- the name is split across labels at a wrap point, and the matcher asks
whether any one label carries the whole name. So the arm answered "lock it" on
every reading with three, two and one targets already locked, and every cascade
died on `Could not find menu entry with text equal 'Lock Target'` because the
client was offering `Unlock Target`. `TheCalledTargetIsRecognisedAsLockedTest`
builds exactly that reading -- an overview row carrying the client's own
`targetedByMeIndicator` and a bar wrapping the name -- and asserts the arm
answers `Nothing`, which is what puts the reading back in reach of the drones
and the guns.

**The counter.** `weaponsAskedReadings` advanced from state alone -- something
locked, some module not cycling -- without asking whether `fireOnActiveTarget`
had run, so while the broadcast arm held every reading the budget still ran out
and the status line reported `GAVE UP after 46 readings` on an arm that had
never been asked once. It now advances only on
`weaponsAnswersThatSpendAReading`, and `TheAnswersThatSpendAReadingTest` asks
that question of every constructor.

Confirmed by mutation, ten of them, each failing named cases:

1. `calledTargetIsLocked` reverted to `lockedTargetNamed` alone -- three cases,
   `test_a_locked_called_target_ends_the_ask`,
   `test_the_arm_answers_nothing_so_the_guns_below_it_are_reachable` and
   `test_an_unlocked_called_target_is_still_locked`; and *not*
   `test_a_wrapped_name_is_invisible_to_the_target_bar_matcher`, which is the
   measurement of why rather than a pin on the fix;
2. `calledTargetIsLocked` reduced to the overview row alone --
   `test_the_bar_is_still_a_second_opinion`, which is what makes the second
   opinion a decision rather than leftovers;
3. the `targetedByMe` read swapped for the neighbouring `.targeting` -- the
   same three as (1) plus
   `test_the_broadcast_arm_stands_down_once_the_target_is_locked`;
4. `weaponsAnswersThatSpendAReading` widened to hold `AllWeaponsCycling` --
   `test_no_answer_that_asks_for_nothing_is_counted`,
   `test_a_reading_the_arm_never_reaches_is_not_charged_for_a_click` and
   `test_the_list_holds_that_one_answer_and_nothing_else`;
5. `weaponsAnswersThatSpendAReading` emptied --
   `test_every_answer_that_spends_a_reading_is_counted`,
   `test_the_bound_is_reachable_at_all` and the length case;
6. the memory update advancing on `not (List.isEmpty targets)` again, which is
   the shipped defect exactly --
   `test_the_counter_advances_only_on_the_answers_that_ask`;
7. the veto's `if` neutered inside `weaponsStep` --
   `test_the_friendly_fire_guard_outranks_every_other_answer` and
   `test_a_held_trigger_spends_no_budget`;
8. `friendlyFireVetoesTheGuns` dropped out of `weaponsStepFromReading` -- the
   friendly-fire file's
   `test_the_trigger_refuses_on_its_own_and_not_via_the_lock`, which is where
   #367's property lives;
9. `describeWeaponsAsk` reverted to its own `if` chain --
   `test_the_status_line_reads_the_rule_rather_than_restating_it`;
10. a seventh constructor added to `WeaponsStep` and handled everywhere except
    the counter -- `test_every_constructor_is_classified_one_way_or_the_other`,
    which is the one case that cannot go quiet as the type grows.

The cases run the real `Bot.elm` through `elm repl`, and the readings they ask
about come from the real `EveOnline.ParseUserInterface`. Nothing here reads a
live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    label, node, reading_binding)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The rat all four pilots of #389 looped on, quoted from the status lines in
# the issue. Two words, which is the whole of why the target bar could not
# answer for it.
CALLED = "Centus Black Ops Agent"

# What #303 read off a live client with a rat locked, with this rat's name
# substituted: the bar wraps at the space and adds the distance. Nothing here
# invents the shape.
WRAPPED_IN_THE_BAR = ["Centus Black Ops", "Agent", "14 km"]

ROW_HEIGHT = 16
ROW_PITCH = 20
ROW_TOP = 20


def overview_window(rows):
    """An overview window whose rows carry the client's own lock indicator.

    Each row is `(name, distance, targeted)`. `targeted` puts a
    `targetedByMeIndicator` under the row's `SpaceObjectIcon`, which is where
    `parseOverviewWindowEntry` reads `commonIndications.targetedByMe` from --
    so what the rule is handed is the icon the client draws rather than a
    boolean this file decided.

    The shape is `test_saxrat_learned_lock_range.overview_rows`'; it is rebuilt
    here rather than imported because that helper belongs to the saxrat app's
    fixtures and carries item ids and hidden rows this file has no use for.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (name, distance, targeted) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH
        icon_children = []
        if targeted:
            icon_children.append(
                node("Sprite", {"_name": "targetedByMeIndicator"}))
        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            label(distance, (10, y, 50, ROW_HEIGHT)),
            label(name, (110, y, 150, ROW_HEIGHT)),
            label(name, (310, y, 150, ROW_HEIGHT)),
            node("SpaceObjectIcon", {}, icon_children,
                 region=(2, y, 12, ROW_HEIGHT)),
        ], region=(0, y, 500, ROW_HEIGHT)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def target_bar(targets):
    """The locked-target bar, one `TargetInBar` per entry.

    Each entry is the list of labels the client draws for it, top to bottom --
    which is the field `textsTopToBottom` is built from, and the field whose
    wrapping is what #389 turned on.
    """
    bars = []
    for index, texts in enumerate(targets):
        x = 600 + index * 90
        bars.append(node("TargetInBar", {}, [
            node("Container", {"_name": "barAndImageCont"}, [
                label(text, (x, 40 + line * 12, 80, 12))
                for line, text in enumerate(texts)
            ], region=(x, 40, 80, 60)),
        ], region=(x, 30, 80, 80)))
    return node("TargetsContainer", {}, bars, region=(600, 30, 400, 80))


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    `bringCalledTargetUnderFire` takes a whole `BotDecisionContext`, so a case
    cannot ask it anything without one. Every field of the context here is
    either the shipped default (`defaultBotSettings`, `initBotMemory`) or the
    emptiest value its type has, so nothing in the fixture can decide the answer
    except the reading -- `test_saxrat_approach_by_double_click`'s arrangement,
    for its reason.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "context = \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = initBotMemory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "armFor = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        ' bringCalledTargetUnderFire (context p) "%s")' % CALLED,
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeFor = \\parsed -> armFor parsed"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "ARM STOOD DOWN"',
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-engage-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def step(target_locked="True", inactive_weapon="True", asked=0,
         friendly_fire="False", ship_ui="True"):
    """The shipped weapon rule, as one expression over four facts and a count.

    The veto and the ship UI are facts of the rule since #389 rather than
    conditions wrapped around it, because the memory update advances the
    counter from this rule and anything the arm refuses on that the rule cannot
    see is a reading charged to a budget nobody spent. They default to "the
    guns are free to fire", so the cases below read as being about the fight.
    """
    return ("weaponsStep { friendlyFireHoldsTheTrigger = %s"
            ", shipUIIsShowing = %s, targetLocked = %s"
            ", inactiveWeaponPresent = %s, askedReadings = %s }"
            % (friendly_fire, ship_ui, target_locked, inactive_weapon, asked))


class TheWeaponDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_nothing_locked_means_nothing_to_fire_on(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoTargetToFireOn" % step(target_locked="False")]),
            [True])

    def test_a_locked_target_and_a_silent_weapon_activates_it(self):
        """The whole point: no rat has to be pointing this ship first."""
        self.assertEqual(
            self.repl.evaluate(["%s == ActivateAWeapon" % step()]),
            [True])

    def test_weapons_already_cycling_are_left_alone(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == AllWeaponsCycling" % step(inactive_weapon="False")]),
            [True])

    def test_the_ask_gives_up_at_the_bound(self):
        """#326: a turret that could not activate held that bot's decision for
        262 consecutive readings with the drones out and idle."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ActivateAWeapon"
                 % step(asked="weaponsAskedReadingsBound - 1"),
                 "%s == GaveUpOnWeapons"
                 % step(asked="weaponsAskedReadingsBound"),
                 "%s == GaveUpOnWeapons"
                 % step(asked="weaponsAskedReadingsBound + 50")]),
            [True, True, True])

    def test_the_bound_is_reported_even_while_the_guns_happen_to_be_fine(self):
        """The bound is checked before the state, so a give-up is reported as
        one rather than masked by a fight that happens to be going fine at that
        moment."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnWeapons"
                 % step(inactive_weapon="False",
                        asked="weaponsAskedReadingsBound")]),
            [True])

    def test_the_bound_is_far_from_a_session_and_far_from_a_hiccup(self):
        self.assertEqual(
            self.repl.evaluate(["weaponsAskedReadingsBound == 20"]),
            [True])

    def test_the_friendly_fire_guard_outranks_every_other_answer(self):
        """#367, restated as an answer of the rule: the veto is checked first,
        so no state of the fight can talk the guns into firing past it."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == FriendlyFireHoldsTheTrigger"
                 % step(friendly_fire="True"),
                 "%s == FriendlyFireHoldsTheTrigger"
                 % step(friendly_fire="True", inactive_weapon="False"),
                 "%s == FriendlyFireHoldsTheTrigger"
                 % step(friendly_fire="True",
                        asked="weaponsAskedReadingsBound")]),
            [True, True, True])

    def test_a_docked_reading_has_nothing_to_fire_with(self):
        """`fireOnActiveTarget` refuses without a ship UI, so the rule has to
        know that too -- otherwise the counter bills for it."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoShipUIToFireFrom" % step(ship_ui="False")]),
            [True])


class TheAnswersThatSpendAReadingTest(unittest.TestCase):
    """Which answers the counter advances on -- executed, not read.

    #389's defect is exactly the hole `approachFleetCommanderAnswersThatSpendAReading`
    was built against, arriving by another route: the counter advanced from a
    condition written beside the arm rather than from the arm's own rule, so it
    counted readings on which the arm never ran. Three pilots reported 46, 36
    and 50 readings spent against a bound of 20, on guns that had not been asked
    once.

    So the question is asked exhaustively and of every constructor, which is the
    only form that cannot go quiet when a constructor is added.
    """

    ADVANCES = ("ActivateAWeapon",)
    SILENT = ("FriendlyFireHoldsTheTrigger", "NoShipUIToFireFrom",
              "NoTargetToFireOn", "AllWeaponsCycling", "GaveUpOnWeapons")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_answer_that_spends_a_reading_is_counted(self):
        """One answer dispatches a click, and it is the only one that does."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member %s weaponsAnswersThatSpendAReading" % answer
                 for answer in self.ADVANCES]),
            [True] * len(self.ADVANCES))

    def test_no_answer_that_asks_for_nothing_is_counted(self):
        """The five silent answers, and `AllWeaponsCycling` is the one worth
        reading twice: a fight going fine is not an ask, and charging it is how
        a working engagement talks itself into a give-up."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member %s weaponsAnswersThatSpendAReading" % answer
                 for answer in self.SILENT]),
            [False] * len(self.SILENT))

    def test_the_list_holds_that_one_answer_and_nothing_else(self):
        """Length as well as membership, so a constructor added to the list
        without being thought about is caught rather than absorbed."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.length weaponsAnswersThatSpendAReading == 1"]),
            [True])

    def test_every_constructor_is_classified_one_way_or_the_other(self):
        """The property the two lists above only imply. A constructor added to
        `WeaponsStep` and forgotten here would be silently uncounted, which is
        the #389 defect from the other side -- so the file's own idea of the
        type is checked against the type."""
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        declaration = source[source.index("\ntype WeaponsStep"):]
        declaration = declaration[:declaration.index("\n\n\n")]
        constructors = re.findall(r"^    [=|] (\w+)$", declaration, re.M)
        self.assertEqual(
            sorted(constructors), sorted(self.ADVANCES + self.SILENT))

    def test_the_bound_is_reachable_at_all(self):
        """The property all of the above exists to protect (#34): the one state
        the arm spends a reading in advances the counter, so
        `weaponsAskedReadingsBound` is reachable rather than decorative."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member (%s) weaponsAnswersThatSpendAReading" % step()]),
            [True])

    def test_a_held_trigger_spends_no_budget(self):
        """#367's guard holds the reading in this arm without asking anything
        of the client, and the old counter billed for it -- so a fleetmate in
        the bar could exhaust the guns' allowance before a legitimate target
        was ever locked."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member (%s) weaponsAnswersThatSpendAReading"
                 % step(friendly_fire="True")]),
            [False])

    def test_a_reading_the_arm_never_reaches_is_not_charged_for_a_click(self):
        """Success is never inferred from a dispatched click, and the converse
        holds too: what the counter counts is the arm *asking*, which is the
        one answer that dispatches. A reading that ends in any other answer
        leaves the number where it was."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member (%s) weaponsAnswersThatSpendAReading"
                 % step(inactive_weapon="False"),
                 "List.member (%s) weaponsAnswersThatSpendAReading"
                 % step(target_locked="False"),
                 "List.member (%s) weaponsAnswersThatSpendAReading"
                 % step(ship_ui="False")]),
            [False, False, False])


class TheCalledTargetIsRecognisedAsLockedTest(unittest.TestCase):
    """#389's first defect, against readings the real parser produced.

    Three readings, all naming the same rat on the overview:

    - `locked`: the row carries the client's `targetedByMeIndicator` and the
      target bar wraps the name across two labels, which is the live shape #303
      recorded and the state all four pilots were actually in;
    - `unlocked`: the same row without the indicator and an empty bar;
    - `barOnly`: no indicator, but a bar entry whose single label carries the
      whole name -- the one case the old matcher could see, kept so the second
      opinion is measured rather than assumed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("locked", [
                overview_window([(CALLED, "14 km", True)]),
                target_bar([WRAPPED_IN_THE_BAR]),
            ]),
            reading_binding("unlocked", [
                overview_window([(CALLED, "14 km", False)]),
            ]),
            reading_binding("barOnly", [
                overview_window([(CALLED, "14 km", False)]),
                target_bar([[CALLED, "14 km"]]),
            ]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and an arm answering nothing read alike,
        so what the parser made of each fixture is checked first."""
        self.assertEqual(
            self.repl.evaluate(
                ["locked /= Nothing",
                 "(locked |> Maybe.map (.overviewWindows"
                 " >> List.concatMap .entries >> List.length)) == Just 1",
                 '(locked |> Maybe.andThen (.overviewWindows'
                 ' >> List.concatMap .entries >> List.head'
                 ' >> Maybe.andThen .objectName)) == Just "%s"' % CALLED,
                 "(locked |> Maybe.map (.targets >> List.length)) == Just 1",
                 "(unlocked |> Maybe.map (.targets >> List.length)) == Just 0",
                 "(barOnly |> Maybe.map (.targets >> List.length)) == Just 1"],
                definitions=self.definitions),
            [True] * 6)

    def test_the_client_says_which_row_this_ship_has_locked(self):
        """`targetedByMe` off the row's own `targetedByMeIndicator`, which is
        the fact the whole fix rests on."""
        self.assertEqual(
            self.repl.evaluate(
                ["(locked |> Maybe.andThen (.overviewWindows"
                 " >> List.concatMap .entries >> List.head"
                 " >> Maybe.map (.commonIndications >> .targetedByMe)))"
                 " == Just True",
                 "(unlocked |> Maybe.andThen (.overviewWindows"
                 " >> List.concatMap .entries >> List.head"
                 " >> Maybe.map (.commonIndications >> .targetedByMe)))"
                 " == Just False"],
                definitions=self.definitions),
            [True, True])

    def test_a_wrapped_name_is_invisible_to_the_target_bar_matcher(self):
        """Why the recognition moved. The bar in `locked` holds this rat, and
        `lockedTargetNamed` cannot find it -- the name is across two labels and
        the matcher asks whether any one label carries the whole of it. #303
        read `['Tower Sentry', 'Sansha I', '20 km']` off a live client, which is
        where this fixture's shape comes from.

        This is a measurement of the instrument, not a pin on the behaviour: it
        is what a case has to show before "ask the overview instead" is a fix
        rather than a preference.
        """
        self.assertEqual(
            self.repl.evaluate(
                ['(locked |> Maybe.andThen (lockedTargetNamed "%s"))'
                 " == Nothing" % CALLED,
                 '(barOnly |> Maybe.andThen (lockedTargetNamed "%s"))'
                 " /= Nothing" % CALLED],
                definitions=self.definitions),
            [True, True])

    def test_a_locked_called_target_ends_the_ask(self):
        """The rule itself: the overview row answers, whatever the bar renders.
        """
        self.assertEqual(
            self.repl.evaluate(
                ['(locked |> Maybe.map (calledTargetIsLocked "%s"))'
                 " == Just True" % CALLED,
                 '(unlocked |> Maybe.map (calledTargetIsLocked "%s"))'
                 " == Just False" % CALLED],
                definitions=self.definitions),
            [True, True])

    def test_the_bar_is_still_a_second_opinion(self):
        """A name the bar does carry stands the arm down on its own, so the
        signal that fails on wrapping is kept rather than replaced -- nothing
        in this repo has yet watched `targetedByMeIndicator` come back from a
        real client, and the two go quiet in opposite directions."""
        self.assertEqual(
            self.repl.evaluate(
                ['(barOnly |> Maybe.map (calledTargetIsLocked "%s"))'
                 " == Just True" % CALLED],
                definitions=self.definitions),
            [True])

    def test_the_arm_answers_nothing_so_the_guns_below_it_are_reachable(self):
        """#360's property, which #389 broke by another route: standing down is
        not merely "stops re-locking", it is *the arm answering `Nothing`* so
        the reading reaches `dronesAssistTheCommander` and `fireOnActiveTarget`
        below it. Executed against the reading the four live pilots were in.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["armFor locked == Nothing", "armFor unlocked /= Nothing"],
                definitions=self.definitions),
            [True, True])

    def test_an_unlocked_called_target_is_still_locked(self):
        """The other half: the fix must not be "never lock anything"."""
        answers = self.repl.strings(
            ["describeFor unlocked", "describeFor locked"],
            definitions=self.definitions)
        self.assertIn("Lock the called target '%s'." % CALLED, answers[0])
        self.assertEqual(answers[1], "ARM STOOD DOWN")

    def test_the_lock_and_the_recognition_read_one_row(self):
        """A bot that decides "not locked" off one row and clicks another can
        loop for ever without either half being wrong on its own -- #303's
        lesson, which is what put both on `overviewEntryForPilot`."""
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        for name in ("\ncalledTargetIsLocked calledTarget reading =",
                     "\nlockCalledTarget context calledTarget ="):
            body = source[source.index(name):]
            body = body[:body.index("\n\n\n")]
            self.assertIn("overviewEntryForPilot", body)


class TheDecisionRootReachesTheGunsTest(unittest.TestCase):
    """Source-pinned: the ordering *is* the bug, and it is a shape not a value.

    A test that only exercised `weaponsStep` would have passed on the broken
    bot too -- the rule was never wrong, it was unreachable.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def order_of(self, *needles):
        return [self.source.index(needle) for needle in needles]

    def body_of(self, definition):
        """One declaration, from its definition line to the next blank gap.

        Needles start at a definition line or a `case` arm rather than at a bare
        name, because a name matches inside the doc comments too -- three
        changes in one day were graded against text in a comment.
        """
        body = self.source[self.source.index(definition):]
        return body[:body.index("\n\n\n")]

    def test_the_guns_sit_below_the_drones_and_above_the_gate(self):
        """#326's rule, restated: reaching the drones must never require the
        weapons to read active first. Keeping the guns strictly below the
        drone arm is what makes that true whatever the guns do."""
        drones, guns, gate = self.order_of(
            "case dronesAssistTheCommander context of",
            "case fireOnActiveTarget context of",
            "case accelerationGateStep context of")
        self.assertLess(drones, guns)
        self.assertLess(guns, gate)

    def test_the_broadcast_arm_stands_down_once_the_target_is_locked(self):
        """Answering `Just` here on every reading is what starved everything
        below it, because the banner never clears on its own. The executed
        cases are in `TheCalledTargetIsRecognisedAsLockedTest`; this pins that
        the arm asks the client rather than the bar's rendering, which is the
        distinction #389 turned on."""
        body = self.body_of("bringCalledTargetUnderFire context calledTarget =")
        self.assertIn("calledTargetIsLocked calledTarget", body)
        self.assertIn("Nothing", body)
        recognition = self.body_of("calledTargetIsLocked calledTarget reading =")
        self.assertIn("targetedByMe", recognition)

    def test_the_fallback_leaves_the_drones_out_while_something_is_locked(self):
        self.assertIn(
            "A target is locked -- leaving the drones out.", self.source)

    def test_it_only_claims_to_leave_the_drones_out_when_any_are_out(self):
        """#374: this branch said "leaving the drones out" without looking.

        Run 12 printed it four times with fifteen drones in the bay and none in
        space -- a line that reads like a bot deliberately holding its drones
        on the field, describing a bay that never opened. The two outcomes are
        now separate and both are named, so a log distinguishes "drones are out
        and staying out" from "there were never any to recall".
        """
        body = self.body_of("\nfightPointedRatsOrReturnDrones context shipUI =")
        self.assertIn("dronesAreInSpace context.readingFromGameClient", body)
        self.assertIn("A target is locked -- leaving the drones out.", body)
        self.assertIn("no drones are in space -- nothing to recall.", body)

    def test_the_recall_and_the_decline_ask_the_same_question(self):
        """Two copies of "is a drone in space" is how they drift apart, which
        is the defect above: one of them was not asking at all."""
        self.assertIn("dronesAreInSpace : ReadingFromGameClient -> Bool",
                      self.source)
        self.assertEqual(
            self.source.count("dronesAreInSpace context.readingFromGameClient"),
            2,
            "the recall and the decline should both go through the one helper")

    def test_a_give_up_on_the_guns_is_visible_in_the_status_line(self):
        """`fireOnActiveTarget` answers `Nothing` when it gives up, so without
        its own status line a locked target with silent guns would read
        exactly like nothing to shoot."""
        self.assertIn("describeWeaponsAsk context", self.source)
        self.assertIn("Weapons: GAVE UP after ", self.source)

    def test_the_counter_advances_only_on_the_answers_that_ask(self):
        """#102's defect is a counter advanced by one condition and read by
        another, and #389 is what it cost here. The memory update calls
        `weaponsStepFromReading` and tests its answer for membership rather
        than restating the guns' state beside them."""
        update = self.body_of(
            "updateMemoryForNewReadingFromGame context botMemoryBefore =")
        self.assertIn("weaponsStepFromReading", update)
        self.assertIn("List.member weaponsNow weaponsAnswersThatSpendAReading",
                      update)
        self.assertIn("weaponsAskedReadings + 1", update)

    def test_the_arm_and_the_counter_read_one_rule(self):
        """Both sides go through `weaponsStep`, so the number in the status
        line is a count of the readings the arm asked on and nothing else."""
        arm = self.body_of("fireOnActiveTarget context =")
        self.assertIn("weaponsStepFromContext context", arm)
        self.assertNotIn("shipUIModulesToActivateOnTarget", arm)

    def test_the_status_line_reads_the_rule_rather_than_restating_it(self):
        """Three restatements of one condition is how the counter's copy came
        to be the wrong one. `describeWeaponsAsk` now names each answer."""
        body = self.body_of("describeWeaponsAsk context =")
        self.assertIn("case weaponsStepFromContext context of", body)
        for answer in ("FriendlyFireHoldsTheTrigger", "NoShipUIToFireFrom",
                       "NoTargetToFireOn", "GaveUpOnWeapons",
                       "AllWeaponsCycling", "ActivateAWeapon"):
            self.assertIn("        %s ->" % answer, body)

    def test_the_status_line_prints_the_bound_beside_the_count(self):
        """"5 readings" means nothing without the allowance beside it, and the
        give-up line is the one that reported 46 against a bound of 20."""
        body = self.body_of("describeWeaponsAsk context =")
        self.assertIn("weaponsAskedReadingsBound", body)


if __name__ == "__main__":
    unittest.main()
