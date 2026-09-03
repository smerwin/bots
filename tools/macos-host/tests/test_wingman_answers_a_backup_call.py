"""Tests for the wingman reading `needs backup` and closing on the caller.

The bug these pin is one character. `parseBroadcastVerb` tested

    stringContainsIgnoringCase "need backup" rest

and the client renders **`needs backup`** -- third person. `"needs backup"`
does not contain `"need backup"`, because after `need` comes `s` rather than a
space, so the test was false on every reading and every backup call the bot has
ever seen fell through to `Unrecognized`. `Need Backup` is the fleet window's
own **button** label, and WINGMAN.md already carried the rule in its own words:
_a button's wording is not the broadcast's_.

The file was internally inconsistent about it too -- `Need Backup` was still
listed in `broadcastVerbsNotYetRead` while `parseBroadcastVerb` claimed to read
it, so one of the two was wrong on every reading. `At Location` and
`In Position at` were the same disagreement with the halves the other way round:
both wordings were captured live, both are matched and acted on, and the list
went on calling them unread. All three are out of it now, leaving the five
button labels nobody has ever seen rendered.

## What the arm does

`answerTheBackupCall` closes on the caller by whichever of the two mechanisms
the reading offers -- an approach where they have an overview row, the
broadcast banner's own `Fleet Member` -> `Warp to Member` where they do not.
Both are reused rather than rewritten: `ensureShipIsApproaching` is the helper
`approachTheFleetCommander` drives, and
`warpToFleetMateFromTheBroadcastBanner` is the cascade
`warpToFleetMateOnThisGrid` drives for the other two company verbs.

Three properties the cases exist for:

**The trust boundary is fleet membership, not `follow-fleet-broadcast-from`.**
Those are different policies. The setting is `answer-backup-calls`, default
`yes`.

**Every answer that is not an action hands the reading back**, refusals
included, so the arm cannot starve what sits under it while a banner that does
not clear stays up -- #360's lesson. `test_the_reading_falls_through_once_the_
ship_is_closing` runs the real arm and carries a control that must still act.

**In system only.** A backup call names no place, so nothing here routes
anywhere; an out-of-system caller is tried through the banner's cascade like
any other and ends at the bound, with `describeBackupCall` naming
out-of-system as the likely reason and #381 as what would have to answer first.

Confirmed by mutation, each failing a named case:

 1. `needsBackupMarker` reverted to the button's `"need backup"` --
    `test_the_third_person_rendering_is_read` and
    `test_the_colon_form_is_read_too`;
 2. the no-colon path removed, so only `<Sender>: needs backup` parses --
    `test_the_third_person_rendering_is_read`;
 3. `Need Backup` put back into `broadcastVerbsNotYetRead` --
    `test_the_verb_list_and_the_parser_agree`;
 4. `Need Shield` wired into `parseBroadcastVerb` on a guess --
    `test_no_unobserved_verb_is_wired_on_a_guess`;
 5. the trust boundary reverted to `follow-fleet-broadcast-from` --
    `test_the_boundary_is_the_fleet_roster` and
    `test_a_caller_nothing_calls_a_fleet_pilot_is_declined`;
 6. every refusal made to answer `Just (... waitForProgressInGame)` --
    `test_a_refusal_hands_the_reading_back`;
 7. `AlreadyOnTheWayToTheCaller` made to wait rather than hand back --
    `test_the_reading_falls_through_once_the_ship_is_closing`;
 8. the give-up made to wait -- `test_the_give_up_hands_the_reading_back`;
 9. `backupCallAnswersThatSpendAReading` widened to hold every constructor --
    `test_only_the_two_answers_that_act_are_counted`;
10. the bound's comparison moved by one --
    `test_the_bound_is_asked_at_its_boundary`;
11. permission asked after the give-up --
    `test_permission_is_asked_before_the_give_up`;
12. the arm placed below `actOnFleetBroadcast` --
    `test_the_arm_outranks_the_travel_broadcasts`;
13. the arm placed above the retreat --
    `test_the_arm_sits_below_the_retreat_and_the_session_end`;
14. a second copy of the banner cascade written out --
    `test_the_cascade_is_written_once`;
15. `NeedBackup` restored to `fleetMateCallingForCompany`, so the fleet-mate
    warp's counter runs on a call this arm is handling --
    `test_the_backup_verb_no_longer_reaches_the_fleet_mate_warp`;
16. `describeBackupCall` dropped from the status line --
    `test_the_arm_is_visible_in_the_status_line`.

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
from test_saxrat_ported_guards import (  # noqa: E402
    SaxratRepl, label, node, overview)
from test_wingman_orbits_the_fleet_commander import (  # noqa: E402
    ship_ui_indicating)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The commander of the fleet the four live wingmen follow, used here as the
# caller because a two-word character name is what the client actually writes.
CALLER = "Gal Bistot"
STRANGER = "Ang Morage"

# The five button labels nobody has seen rendered. Quoted from the fleet
# window's own `BroadcastButton` tooltips, which is where
# `broadcastVerbsNotYetRead` gets them.
UNOBSERVED_BUTTONS = [
    "Need Armor",
    "Need Capacitor",
    "Need Shield",
    "Request That the Fleet Hold Position",
    "Spotted an Enemy",
]


def reading_binding(name, children):
    """`SaxratRepl.reading_binding`, called rather than copied.

    It names only `EveOnline.MemoryReading` and `EveOnline.ParseUserInterface`,
    which resolve in whichever app's tree the repl was built from, so it builds
    a real wingman reading as readily as a saxrat one.
    """
    return SaxratRepl.reading_binding(name, children)


def fleet_window(banner=None, member_rows=()):
    """A `FleetWindow` the real parser accepts, with an optional banner.

    `fleetBroadcastBannerText` filters the window's descendants for
    `_name = "bannerLabel"` and reads the display text off it, and
    `fleetMemberNames` wants `_name = "entryLabel"` -- so the two channels are
    told apart by the client's own names rather than by anything this file
    decides. The header carries no pilot label, so `fleetPilotNames` gets its
    names from the member rows alone and the commander fallback (which is
    `List.head follow-fleet-broadcast-from`, empty in these fixtures) cannot
    quietly add one.
    """
    children = [
        node("FleetHeaderContainer", {}, [
            label("Fleet (5)", (10, 10, 200, 16)),
        ], region=(0, 0, 300, 30)),
    ]

    if banner is not None:
        children.append(
            node("FleetBroadcastCont", {}, [
                node("EveLabelMedium",
                     {"_name": "bannerLabel", "_setText": banner},
                     region=(10, 40, 280, 16)),
            ], region=(0, 34, 300, 24)))

    children += [
        node("FleetMember", {}, [
            node("EveLabelMedium",
                 {"_name": "entryLabel", "_setText": row},
                 region=(10, 100 + index * 20, 200, 16)),
        ], region=(0, 100 + index * 20, 300, 20))
        for index, row in enumerate(member_rows)]

    return node("FleetWindow", {}, children, region=(0, 0, 300, 400))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def declaration(source, name):
    """One top-level declaration, doc comment stripped.

    Sliced on the signature line and ended at the next top-level declaration,
    so a claim about a rule's body cannot be satisfied by prose above it.
    """
    anchor = "\n%s :" % name
    assert anchor in source, name
    start = source.index(anchor) + 1
    rest = source[start:]
    end = rest.index("\n\n\n") if "\n\n\n" in rest else len(rest)
    return rest[:end]


def indented_block(source, header):
    """From `header` to the next line indented no further than `header` is.

    The readers that stop at a blank line or at a record's opening brace have
    already cost four PRs an assertion that passed having read nothing, so this
    slices by indentation -- `answerTheBackupCall`'s branches build records and
    its `case` arms are separated by blank lines.
    """
    assert header in source, header
    start = source.index(header)
    first = header.split("\n")[-1]
    indent = len(first) - len(first.lstrip())
    lines = source[start:].split("\n")
    while lines and not lines[0].strip():
        lines = lines[1:]
    out = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        out.append(line)
    return "\n".join(out)


def step(setting="True", in_fleet="True", on_grid="True", warping="False",
         approaching="False", asked=0):
    """The shipped rule, as one expression over five facts and a count."""
    return ("backupCallStep { settingIsYes = %s, callerIsInThisFleet = %s"
            ", callerIsOnThisGrid = %s, shipIsWarpingOrJumping = %s"
            ", shipIsApproaching = %s, askedReadings = %s }"
            % (setting, in_fleet, on_grid, warping, approaching, asked))


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    `answerTheBackupCall` takes a whole `BotDecisionContext` and a `ShipUI`, so
    a case cannot ask it anything without both. Every field of the context is
    either the shipped default (`defaultBotSettings`, `initBotMemory`) or the
    emptiest value its type has, so nothing in the fixture can decide the answer
    except the reading -- `test_wingman_engages_the_called_target`'s
    arrangement, for its reason. The `ShipUI` comes out of the same really
    parsed reading, so the arm is handed what the bot would have been handed.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.PromptParser",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "settingsWith = \\answer ->"
        " { defaultBotSettings | answerBackupCalls = answer }",
        "contextWith = \\answer parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = settingsWith answer"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = initBotMemory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "armWith = \\answer parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.shipUI |> Maybe.andThen (answerTheBackupCall (contextWith answer p)))",
        "armFor = armWith Common.PromptParser.Yes",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeWith = \\answer parsed -> armWith answer parsed"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "ARM STOOD DOWN"',
        "describeFor = describeWith Common.PromptParser.Yes",
        "clauseFor = \\parsed -> parsed"
        ' |> Maybe.map (\\p -> describeBackupCall (contextWith Common.PromptParser.Yes p))'
        ' |> Maybe.withDefault "NO READING"',
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-backup-call-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


class TheMatcherCarriesTheBroadcastsWordingTest(unittest.TestCase):
    """#385 itself, executed rather than restated."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parsed(self, banner):
        return self.repl.strings(
            ['case parseFleetBroadcast "%s" of\n'
             "    NeedBackup { pilot } ->\n"
             '        "NeedBackup " ++ pilot\n'
             "    Unrecognized text ->\n"
             '        "Unrecognized " ++ text\n'
             "    TravelTo { pilot, destination } ->\n"
             '        "TravelTo " ++ pilot ++ " -> " ++ destination\n'
             "    AtLocation { pilot, system } ->\n"
             '        "AtLocation " ++ pilot ++ " -> " ++ system\n'
             "    InPositionAt { pilot, gate } ->\n"
             '        "InPositionAt " ++ pilot ++ " -> " ++ gate\n'
             "    JumpGate { pilot, gate } ->\n"
             '        "JumpGate " ++ pilot ++ " -> " ++ gate\n'
             "    AlignGate { pilot, gate } ->\n"
             '        "AlignGate " ++ pilot ++ " -> " ++ gate\n'
             "    CalledTarget target ->\n"
             '        "CalledTarget " ++ target' % banner])[0]

    def test_the_one_character_is_the_whole_defect(self):
        """Executed in Elm, because it is the reason for the change: the
        button's wording is not a substring of the broadcast's."""
        self.assertEqual(
            self.repl.evaluate(
                ['String.contains "need backup" "needs backup" == False',
                 'String.contains "needs backup" "needs backup" == True']),
            [True, True])

    def test_the_third_person_rendering_is_read(self):
        """The shape the client draws: no colon, verb in the third person."""
        self.assertEqual(self.parsed("%s needs backup" % CALLER),
                         "NeedBackup " + CALLER)

    def test_the_colon_form_is_read_too(self):
        """The issue's own quote elides the sender, and both shapes occur in
        this client's observed vocabulary -- `<Sender>: Travel to X` beside
        `<Sender> is at location X`. Covering both is what makes the fix
        independent of which one `...needs backup` was."""
        self.assertEqual(self.parsed("%s: needs backup" % CALLER),
                         "NeedBackup " + CALLER)

    def test_the_sender_carries_no_colon_into_the_name(self):
        """The colon form is tried first, so the no-colon matcher can never cut
        a sender with the colon still stuck to it -- and this bot matches a
        pilot name exactly, so `'Gal Bistot:'` would match nobody."""
        self.assertEqual(self.parsed("%s: needs backup" % CALLER),
                         "NeedBackup " + CALLER)

    def test_the_wording_is_matched_whatever_its_case(self):
        self.assertEqual(self.parsed("%s NEEDS BACKUP" % CALLER),
                         "NeedBackup " + CALLER)

    def test_the_buttons_own_wording_is_not_read(self):
        """`Broadcast: Need Backup` is the button. Reading it as a broadcast is
        the mistake #385 was filed on, and matching it now would put the button's
        wording back into the matcher on no evidence at all."""
        self.assertTrue(self.parsed("%s: Need Backup" % CALLER)
                        .startswith("Unrecognized"))

    def test_a_call_with_no_sender_names_nobody_to_fly_to(self):
        """`Unrecognized` is the better answer: it opens the broadcast's own
        menu, which is how an unread wording gets captured."""
        self.assertTrue(self.parsed("needs backup").startswith("Unrecognized"))

    def test_the_other_verbs_are_undisturbed(self):
        """The no-colon path is reached only once every colon shape has been
        tried, so nothing above it can be stolen by it."""
        self.assertEqual(
            [self.parsed("Target Heather Hemorphite (Tristan)"),
             self.parsed("%s: Travel to Riramia" % CALLER),
             self.parsed("%s: Jump Stargate Bhizheba" % CALLER),
             self.parsed("%s: Align Stargate Bhizheba" % CALLER),
             self.parsed("%s is at location Amarr" % CALLER),
             self.parsed("%s is in position at Stargate Amarr" % CALLER)],
            ["CalledTarget Heather Hemorphite",
             "TravelTo %s -> Riramia" % CALLER,
             "JumpGate %s -> Bhizheba" % CALLER,
             "AlignGate %s -> Bhizheba" % CALLER,
             "AtLocation %s -> Amarr" % CALLER,
             "InPositionAt %s -> Amarr" % CALLER])

    def test_the_verb_list_and_the_parser_agree(self):
        """The file was internally inconsistent: `Need Backup` was listed as
        unread while the matcher claimed to read it. One of those was wrong on
        every reading.

        `At Location` and `In Position at` were the same disagreement with the
        halves the other way round -- both wordings were captured live and both
        are acted on, while the list went on calling them unread. A list that
        names a verb the parser reads is a list nobody can check the parser
        against, which is how one wrong matcher sat in it unnoticed.
        """
        self.assertEqual(
            self.repl.evaluate(
                ['List.member "Need Backup" broadcastVerbsNotYetRead == False',
                 'List.member "At Location" broadcastVerbsNotYetRead == False',
                 'List.member "In Position at" broadcastVerbsNotYetRead == False',
                 "List.length broadcastVerbsNotYetRead == 5"]),
            [True] * 4)

    def test_no_unobserved_verb_is_wired_on_a_guess(self):
        """The other five are button labels and none has been observed
        rendered. Wiring one from the button list is precisely what produced
        this bug, so each must still be listed and must parse as nothing --
        in the button's own wording and in the third person a guesser would
        reach for."""
        expressions = []
        for button in UNOBSERVED_BUTTONS:
            expressions.append(
                'List.member "%s" broadcastVerbsNotYetRead' % button)
        answers = self.repl.evaluate(expressions)
        self.assertEqual(answers, [True] * len(UNOBSERVED_BUTTONS))

        for button in UNOBSERVED_BUTTONS:
            with self.subTest(button=button):
                for banner in ("%s: %s" % (CALLER, button),
                               "%s %ss" % (CALLER, button.lower())):
                    self.assertTrue(
                        self.parsed(banner).startswith("Unrecognized"),
                        banner)


class TheBackupCallRuleTest(unittest.TestCase):
    """`backupCallStep`, executed at every clause it has."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_setting_switches_the_arm_off(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == BackupCallsAreOff" % step(setting="False")]),
            [True])

    def test_a_caller_nothing_calls_a_fleet_pilot_is_declined(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == TheCallerIsNotAFleetPilot" % step(in_fleet="False")]),
            [True])

    def test_a_caller_on_this_grid_is_approached(self):
        self.assertEqual(
            self.repl.evaluate(["%s == ApproachTheCaller" % step()]),
            [True])

    def test_a_caller_off_this_grid_is_warped_to(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == WarpToTheCallerFromTheBroadcast"
                 % step(on_grid="False")]),
            [True])

    def test_a_ship_already_approaching_is_left_alone(self):
        """The client's own `ManeuverApproach` is the only thing that stops the
        ask; a dispatched click is not a manoeuvre."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == AlreadyOnTheWayToTheCaller" % step(approaching="True")]),
            [True])

    def test_a_ship_already_warping_is_left_alone(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == AlreadyOnTheWayToTheCaller" % step(warping="True"),
                 "%s == AlreadyOnTheWayToTheCaller"
                 % step(warping="True", on_grid="False")]),
            [True, True])

    def test_the_bound_is_asked_at_its_boundary(self):
        """Both sides of the comparison, and a fixed value far past it so that
        a constant admitting everything cannot satisfy the pair."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachTheCaller"
                 % step(asked="(backupCallAskedReadingsBound - 1)"),
                 "%s == GaveUpOnTheBackupCall"
                 % step(asked="backupCallAskedReadingsBound"),
                 "%s == GaveUpOnTheBackupCall" % step(asked=9999),
                 "%s == ApproachTheCaller" % step(asked=0),
                 "4 < backupCallAskedReadingsBound"]),
            [True] * 5)

    def test_the_bound_is_the_fleet_mate_warps_own(self):
        """One number for one mechanism: this arm drives the same banner
        cascade that bound was sized for."""
        self.assertEqual(
            self.repl.evaluate(
                ["backupCallAskedReadingsBound"
                 " == fleetMateWarpAskedReadingsBound"]),
            [True])
        self.assertIn(
            "backupCallAskedReadingsBound = fleetMateWarpAskedReadingsBound",
            collapsed(declaration(source_of(WINGMAN_BOT_ELM),
                                  "backupCallAskedReadingsBound")))

    def test_permission_is_asked_before_the_give_up(self):
        """`approachFleetCommanderStep`'s ordering and its reason: a session
        that never permits a call must not read as one that gave up on one."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == BackupCallsAreOff" % step(setting="False", asked=9999),
                 "%s == TheCallerIsNotAFleetPilot"
                 % step(in_fleet="False", asked=9999)]),
            [True, True])

    def test_only_the_two_answers_that_act_are_counted(self):
        """A refusal, a give-up and a ship already closing all dispatch
        nothing, so none may spend the budget."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member ApproachTheCaller"
                 " backupCallAnswersThatSpendAReading",
                 "List.member WarpToTheCallerFromTheBroadcast"
                 " backupCallAnswersThatSpendAReading",
                 "List.length backupCallAnswersThatSpendAReading == 2"]),
            [True, True, True])
        self.assertEqual(
            self.repl.evaluate(
                ["List.member %s backupCallAnswersThatSpendAReading == False"
                 % answer
                 for answer in ("BackupCallsAreOff", "TheCallerIsNotAFleetPilot",
                                "GaveUpOnTheBackupCall",
                                "AlreadyOnTheWayToTheCaller")]),
            [True] * 4)

    def test_every_constructor_is_classified_one_way_or_the_other(self):
        """The one case that cannot go quiet as the type grows."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.all"
                 " (\\answer -> List.member answer backupCallAnswersThatSpendAReading"
                 " || List.member answer"
                 " [ BackupCallsAreOff, TheCallerIsNotAFleetPilot"
                 " , GaveUpOnTheBackupCall, AlreadyOnTheWayToTheCaller ])"
                 " [ BackupCallsAreOff, TheCallerIsNotAFleetPilot"
                 " , GaveUpOnTheBackupCall, AlreadyOnTheWayToTheCaller"
                 " , ApproachTheCaller, WarpToTheCallerFromTheBroadcast ]"]),
            [True])


class TheArmActsOnARealReadingTest(unittest.TestCase):
    """The real arm, over readings the real parser produced.

    Four fixtures, and each is one of the arm's answers:

    - `onGrid`: the banner calls backup, the caller is a fleet member row, and
      they have an overview row this ship is not approaching;
    - `closing`: the same reading with the client naming `Approach`, which is
      the only thing that stops the ask;
    - `offGrid`: the banner and the member row, and no overview row at all;
    - `stranger`: the banner names somebody no member row, header or chat icon
      calls a fleet pilot.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("onGrid", [
                fleet_window(banner="%s needs backup" % CALLER,
                             member_rows=[CALLER]),
                overview([("14 km", CALLER, "Coercer")]),
                ship_ui_indicating(None),
            ]),
            reading_binding("closing", [
                fleet_window(banner="%s needs backup" % CALLER,
                             member_rows=[CALLER]),
                overview([("14 km", CALLER, "Coercer")]),
                ship_ui_indicating("Approach"),
            ]),
            reading_binding("offGrid", [
                fleet_window(banner="%s needs backup" % CALLER,
                             member_rows=[CALLER]),
                overview([("14 km", "Centii Devourer", "Frigate")]),
                ship_ui_indicating(None),
            ]),
            reading_binding("stranger", [
                fleet_window(banner="%s needs backup" % STRANGER,
                             member_rows=[CALLER]),
                overview([("14 km", STRANGER, "Coercer")]),
                ship_ui_indicating(None),
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
                ["onGrid /= Nothing",
                 "(onGrid |> Maybe.andThen .shipUI) /= Nothing",
                 "(onGrid |> Maybe.andThen fleetBroadcastBannerText)"
                 ' == Just "%s needs backup"' % CALLER,
                 "(onGrid |> Maybe.map (fleetPilotNamesFromReading []))"
                 ' == Just [ "%s" ]' % CALLER,
                 "(onGrid |> Maybe.andThen (overviewEntryForPilot \"%s\"))"
                 " /= Nothing" % CALLER,
                 "(offGrid |> Maybe.andThen (overviewEntryForPilot \"%s\"))"
                 " == Nothing" % CALLER,
                 "(closing |> Maybe.map shipIsApproachingFromReading)"
                 " == Just True",
                 "(onGrid |> Maybe.map shipIsApproachingFromReading)"
                 " == Just False",
                 "(stranger |> Maybe.map (fleetPilotNamesFromReading []))"
                 ' == Just [ "%s" ]' % CALLER],
                definitions=self.definitions),
            [True] * 9)

    def test_a_caller_on_this_grid_is_approached(self):
        answer = self.repl.strings(["describeFor onGrid"],
                                   definitions=self.definitions)[0]
        self.assertIn("'%s' needs backup" % CALLER, answer)
        self.assertIn("approach them", answer)

    def test_a_caller_off_this_grid_is_warped_to_from_the_banner(self):
        answer = self.repl.strings(["describeFor offGrid"],
                                   definitions=self.definitions)[0]
        self.assertIn("'%s' needs backup" % CALLER, answer)
        self.assertIn("not on this grid", answer)
        self.assertIn("broadcast banner", answer)

    def test_the_reading_falls_through_once_the_ship_is_closing(self):
        """#360's property. Standing down is not merely "stops re-asking", it
        is *the arm answering `Nothing`* so the reading reaches the drones, the
        guns and the gate below it -- and the control beside it is a reading
        that must still act, so an arm that answered `Nothing` for everything
        could not pass."""
        self.assertEqual(
            self.repl.evaluate(
                ["armFor closing == Nothing", "armFor onGrid /= Nothing"],
                definitions=self.definitions),
            [True, True])

    def test_a_refusal_hands_the_reading_back(self):
        """A call this ship will not answer is nothing more to do about the
        call, not a reason to spend the reading saying so. Both refusals, with
        the same control."""
        self.assertEqual(
            self.repl.evaluate(
                ["armFor stranger == Nothing",
                 "armWith Common.PromptParser.No onGrid == Nothing",
                 "armFor onGrid /= Nothing"],
                definitions=self.definitions),
            [True, True, True])

    def test_the_boundary_is_the_fleet_roster(self):
        """`stranger` differs from `onGrid` in one thing only: whose name the
        banner carries against the fleet window's member rows. Neither reading
        names anybody in `follow-fleet-broadcast-from`, which is empty in both,
        so an arm gated on that allowlist would decline both."""
        self.assertEqual(
            self.repl.evaluate(
                ["armFor onGrid /= Nothing",
                 "armFor stranger == Nothing",
                 "List.isEmpty defaultBotSettings.followFleetBroadcastFrom"],
                definitions=self.definitions),
            [True, True, True])

    def test_the_arm_says_which_refusal_it_made(self):
        """`describeBackupCall` is what a `Nothing` cannot carry."""
        clauses = self.repl.strings(
            ["clauseFor stranger", "clauseFor onGrid", "clauseFor closing"],
            definitions=self.definitions)
        self.assertIn("in this fleet", clauses[0])
        self.assertIn(STRANGER, clauses[0])
        self.assertIn("approaching '%s'" % CALLER, clauses[1])
        self.assertIn("on the way to '%s'" % CALLER, clauses[2])

    SPENT_CONTEXT = (
        "spentContext = \\p ->\n"
        "    let\n"
        "        base =\n"
        "            contextWith Common.PromptParser.Yes p\n"
        "    in\n"
        "    { base | memory ="
        " { initBotMemory | backupCallAskedReadings = 9999 } }"
    )

    def test_the_give_up_hands_the_reading_back(self):
        """A give-up that waits is not a give-up: this arm sits above the whole
        fight, so parking on `waitForProgressInGame` would be #321's "a branch
        at the head of the tree with no bound owns the whole bot" with a
        politer status line. Asked through the real arm on a real reading, with
        the counter wound past the bound, and with the control beside it."""
        self.assertEqual(
            self.repl.evaluate(
                ["(onGrid |> Maybe.andThen (\\p ->"
                 " p.shipUI |> Maybe.andThen"
                 " (answerTheBackupCall (spentContext p)))) == Nothing",
                 "armFor onGrid /= Nothing"],
                definitions=self.definitions + [self.SPENT_CONTEXT]),
            [True, True])

    def test_the_give_up_names_out_of_system_and_the_issue(self):
        """The honest scope is in-system: a backup call names no place, so
        nothing here can route to one. The give-up says so rather than the arm
        waiting silently, and it names #381 as what would have to answer
        first."""
        clause = self.repl.strings(
            ["(onGrid |> Maybe.map (\\p -> describeBackupCall"
             ' (spentContext p))) |> Maybe.withDefault "NO READING"'],
            definitions=self.definitions + [self.SPENT_CONTEXT])[0]
        self.assertIn("GAVE UP after 9999 readings", clause)
        self.assertIn(CALLER, clause)
        self.assertIn("not in this system", clause)
        self.assertIn("#381", clause)


class TheWiringTest(unittest.TestCase):
    """Read out of the source, through readers that cannot pass on nothing."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(WINGMAN_BOT_ELM)

    def root(self):
        root = self.source[self.source.index(
            "\nwingmanDecisionRootInSpace context shipUI ="):]
        return root[:root.index("\n\n\n{-|")]

    def test_the_arm_outranks_the_travel_broadcasts(self):
        """#237's argument: being slow to a backup call costs a ship where
        being slow to an `is at location` costs a few seconds of alignment."""
        root = self.root()
        self.assertIn("answerTheBackupCall context shipUI", root)
        self.assertIn("actOnFleetBroadcast context shipUI", root)
        self.assertLess(root.index("answerTheBackupCall context shipUI"),
                        root.index("actOnFleetBroadcast context shipUI"))

    def test_the_arm_sits_below_the_retreat_and_the_session_end(self):
        """As everything here does: a ship past its own threshold leaves rather
        than joining somebody else's fight.

        `manageMiddleRowModules` joined this list when #398 landed while #385
        was in flight, and it is the one the rebase had to decide: both arms
        wanted the slot directly under `unlockFleetPilotInTargetBar`. #394's
        own argument settles it -- a hardener or a prop mod is worth a reading
        while the ship is staying, and this arm is the first that decides to
        go somewhere -- so the module step stays whole and this sits under it,
        still above the travel broadcasts. #400 later removed the module
        step's tooltip-matched sibling, `activateAlwaysOnModules`, since it
        could never fire; `manageMiddleRowModules` is the whole of the step
        now.
        """
        root = self.root()
        for above in ("sessionIsEnding context shipUI",
                      "retreatToTheCommander context shipUI",
                      "recoverFromRetreat context shipUI",
                      "unlockFleetPilotInTargetBar context",
                      "manageMiddleRowModules context"):
            with self.subTest(above=above):
                self.assertIn(above, root)
                self.assertLess(root.index(above),
                                root.index("answerTheBackupCall context shipUI"))

    def test_the_backup_verb_no_longer_reaches_the_fleet_mate_warp(self):
        """`fleetMateCallingForCompany` feeds `goToFleetMateWarpAskedReadings`
        and `describeFleetMateWarp`. Leaving `NeedBackup` in it would have that
        counter advancing and that clause reporting a warp no branch was
        attempting -- a status line disagreeing with the decision."""
        body = declaration(self.source, "fleetMateCallingForCompany")
        self.assertIn("AtLocation", body)
        self.assertIn("InPositionAt", body)
        self.assertNotIn("NeedBackup", body)
        self.assertIn('say "Handled above -- a backup call reaches its own branch."',
                      collapsed(indented_block(
                          self.source, "        NeedBackup _ ->")))

    def test_the_cascade_is_written_once(self):
        """One cascade, two callers.

        The client offers `Warp to Member` in two places and which one is
        contextual -- directly on a `needs backup` banner, inside the
        `Fleet Member` submenu otherwise, both read live off the same element.
        So the cascade takes either, and what must not drift is the
        **exactness**: `"Warp to Member"` is a prefix of
        `"Warp to Member Within"`, and a containing match at either rung takes
        the wrong entry.
        """
        cascade = collapsed(declaration(
            self.source, "warpToMemberFromTheBroadcastBanner"))
        self.assertIn("menuEntryIsWarpToMember", cascade)
        self.assertIn('menuEntryTextEquals "Fleet Member"', cascade)
        self.assertIn('useMenuEntryWithTextEqual "Warp to Member"', cascade)
        for loose in ("stringContainsIgnoringCase", "String.contains",
                      "String.startsWith"):
            with self.subTest(loose=loose):
                self.assertNotIn(loose, cascade)
        self.assertEqual(
            self.source.count("warpToMemberFromTheBroadcastBanner =\n"), 1)
        for caller in ("warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =",
                       "answerTheBackupCall context shipUI ="):
            with self.subTest(caller=caller):
                self.assertIn("warpToFleetMateFromTheBroadcastBanner",
                              indented_block(self.source, "\n" + caller))

    def test_the_approach_is_the_shared_helper(self):
        """Reuse rather than a second approach: `ensureShipIsApproaching` is
        what `approachTheFleetCommander` drives, and its confirmation is the
        client's own `ManeuverApproach`."""
        arm = indented_block(self.source, "\nanswerTheBackupCall context shipUI =")
        self.assertIn("ensureShipIsApproaching", arm)
        for invented in ("EffectOnWindow.KeyDown", "mouseDoubleClickOnUIElement",
                         "ManeuverApproach"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, arm)

    def test_the_counter_advances_from_the_shipped_rule(self):
        """#102: a counter advanced by one condition and read by another is two
        rules on two schedules."""
        update = self.source[self.source.index(
            "\nupdateMemoryForNewReadingFromGame "):]
        update = update[:update.index("\n\n\n")]
        self.assertIn("backupCallStepFromReading", update)
        arm = collapsed(indented_block(
            update, "    , backupCallAskedReadings ="))
        self.assertIn("List.member step backupCallAnswersThatSpendAReading",
                      arm)
        self.assertIn("botMemoryBefore.backupCallAskedReadings + 1", arm)
        self.assertIn("step == GaveUpOnTheBackupCall", arm)

    def test_the_arm_is_visible_in_the_status_line(self):
        status = self.source[self.source.index("\nstatusTextFromState context ="):]
        status = status[:status.index("\n\n\n")]
        self.assertIn("describeBackupCall context", status)

    def test_the_setting_is_parsed_and_defaults_to_yes(self):
        settings = self.source[self.source.index("\nparseBotSettings :"):]
        settings = settings[:settings.index("\n\n\n")]
        self.assertIn('( "answer-backup-calls"', settings)
        self.assertIn("PromptParser.valueTypeYesOrNo", settings)
        defaults = self.source[self.source.index("\ndefaultBotSettings ="):]
        defaults = defaults[:defaults.index("\n\n\n")]
        self.assertIn("answerBackupCalls = PromptParser.Yes", defaults)

    def test_the_setting_is_documented_where_help_reads_it(self):
        """`bot_help.py` generates `--help` from the header's own bullets."""
        header = self.source[:self.source.index("\nmodule Bot ")]
        self.assertIn("`answer-backup-calls`", header)
        self.assertIn("needs backup", header)


class TheSettingIsParsedForRealTest(unittest.TestCase):
    """The parser, asked rather than read."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parsed(self, settings):
        return self.repl.strings(
            ['case parseBotSettings "%s" of\n'
             "    Err error ->\n"
             '        "Err " ++ error\n'
             "    Ok settings ->\n"
             "        case settings.answerBackupCalls of\n"
             "            Common.PromptParser.Yes ->\n"
             '                "yes"\n'
             "            Common.PromptParser.No ->\n"
             '                "no"' % settings])[0]

    def test_the_default_answers_backup_calls(self):
        """A fleet that has a wingman should get help from it, and this
        session's owner has twice chosen that a survival behaviour should not
        be opt-in."""
        self.assertEqual(self.parsed(""), "yes")

    def test_it_can_be_switched_off(self):
        self.assertEqual(self.parsed("answer-backup-calls = no"), "no")

    def test_it_can_be_asked_for_explicitly(self):
        self.assertEqual(self.parsed("answer-backup-calls = yes"), "yes")

    def test_a_value_it_cannot_read_ends_the_session(self):
        """Every unusable value in these bots costs a session rather than being
        guessed at."""
        self.assertTrue(self.parsed("answer-backup-calls = maybe")
                        .startswith("Err"))


if __name__ == "__main__":
    unittest.main()
