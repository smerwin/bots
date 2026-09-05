"""The gas huffer's scaffold: its settings, its fail-closed tag, and the two
recoveries that have to be armed before any behaviour is written on top.

Issue #459, under #456. The app is `eve-online-gas-huffer` and it harvests
nothing yet -- #460 through #464 are the behaviour. What this file pins is
everything that has to be right *before* that arrives, because each of these is
a thing a later change would inherit silently rather than notice.

**`friendly-ship-tag` unset means every ship reads hostile.** That is the one
setting whose default direction is a safety property rather than a convenience,
and it is executed here rather than asserted in prose: `shipReadsFriendly` is
run through the real `Bot.elm` against a list of names, with no tag set, and
every one has to come back `False`. Flipping `hostileTrustFromSettings`'
`Nothing` branch to a permissive answer fails
`TheUnsetTagTrustsNobodyTest.test_with_no_tag_every_ship_reads_hostile` by name.

**Every string setting refuses an empty value.** PR #116's rule, and two of the
five would be actively dangerous without it -- `gas-cloud-name-prefix=` makes
`String.startsWith ""` true of every row on the grid, and `friendly-ship-tag=`
makes `stringContainsIgnoringCase ""` true of every ship, which is the exact
inversion of the paragraph above reached by a missing keystroke rather than by
a changed default. The guard is asked through the real parser *and* directly,
because `parseSimpleListOfAssignments` trims every value before a handler sees
it -- so a guard with no trim of its own passes the end-to-end case, which is
the hole #113 found by mutation.

**`closeSystemSettingsMenu` is first in the setup list.** Not polish: EVE's own
Settings/pause menu covers the screen and silently absorbs every click meant for
the game underneath, a naked Escape opens it, and this bot presses Escape at a
message box that will not close. The symptom is "clicks are not landing" rather
than "a menu is open", and it cost the operator several minutes each time it
happened while #456's findings were being gathered by hand. Its **reachability**
is executed as well as its placement: a tree carrying the menu's own
`l_systemmenu` layer and its `closeMenuClick` button answers `Just`, and one
without answers `Nothing`, both through the real
`EveOnline.ParseUserInterface`. A guard that cannot fire in the state it runs in
is this repo's signature bug (#15, #34, #42) and a placement case alone would
not see it.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies fetched, which is what `compile_bot.sh`
leaves behind; without it they **fail** rather than skipping, for the reason
`prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import ElmRepl, elm_json_literal, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
APPLICATIONS_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online")
GAS_HUFFER_DIR = os.path.join(APPLICATIONS_DIR, "eve-online-gas-huffer")
SAXRAT_DIR = os.path.join(APPLICATIONS_DIR, "eve-online-saxrat")
GAS_HUFFER_BOT_ELM = os.path.join(GAS_HUFFER_DIR, "Bot.elm")
RUN_GAS_HUFFER = os.path.join(MACOS_HOST_DIR, "run_gas_huffer.sh")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    "import Result.Extra",
)

# Every setting whose value names one thing, with the field it fills. All five
# take `valueTypeNonEmptyString`; the two integer settings are checked
# separately, since `AppSettings.valueTypeInteger` already refuses an empty
# value and this file must not claim credit for that.
NAME_SETTINGS = {
    "anomaly-group": "anomalyGroup",
    "anomaly-name": "anomalyName",
    "gas-cloud-name-prefix": "gasCloudNamePrefix",
    "home-structure-name": "homeStructureName",
    "retreat-bookmark-prefix": "retreatBookmarkPrefix",
    "friendly-ship-tag": "friendlyShipTag",
}

INTEGER_SETTINGS = ("dscan-interval-seconds", "bot-step-delay")

# Obviously fictional, and deliberately so: nothing naming a real corporation,
# structure, system or pilot goes in this repository, which is #456's own rule
# and the reason `run_gas_huffer.sh` ships no settings at all.
FICTIONAL_TAG = "[EXMPL]"
FICTIONAL_STRUCTURE = "Example Refinery"

# Ship names to ask the trust rule about with no tag configured. Two of them are
# the awkward ones: the empty string, which is what an unguarded empty setting
# would have matched against, and a name that literally contains the fictional
# tag, so a rule that had somehow retained a tag would answer `True` for it.
SHIP_NAMES = [
    "Somebody Else",
    "",
    FICTIONAL_TAG + " Somebody Else",
    "unfamiliar hauler",
]

_address = iter(range(100000, 999999))


def node(type_name, entries=None, children=(), region=None):
    """One UI tree node in the shape `decodeMemoryReadingFromString` wants."""
    dict_entries = dict(entries or {})
    if region is not None:
        x, y, width, height = region
        dict_entries.update({
            "_displayX": x, "_displayY": y,
            "_displayWidth": width, "_displayHeight": height,
        })
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": dict_entries,
        "children": list(children),
    }


def system_menu_layer():
    """The client's own pause-menu layer, with the close button in its header.

    Both halves are what `closeSystemSettingsMenu` navigates by: the layer's
    `_name` is `l_systemmenu` and the button's `_elementId` is `closeMenuClick`,
    which saxrat's copy records as the stable, page-independent id. Both nodes
    carry a display region, since `listDescendantsWithDisplayRegion` is what the
    branch walks and a node without one is filed where it cannot reach.
    """
    return node("LayerCore", {"_name": "l_systemmenu"}, [
        node("Container", {"_name": "header"}, [
            node("ButtonIcon", {"_elementId": "closeMenuClick"},
                 region=(1840, 40, 32, 32)),
        ], region=(400, 20, 1120, 60)),
    ], region=(0, 0, 1920, 1080))


def ordinary_layer():
    """A layer with no pause menu in it, as a control for the case above."""
    return node("LayerCore", {"_name": "l_main"}, [
        node("Container", {"_name": "somethingElse"},
             region=(400, 20, 1120, 60)),
    ], region=(0, 0, 1920, 1080))


def tree_with(children):
    return node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


def reading_binding(name, children):
    """A `let` binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what a case asserts on is what the bot
    would have been handed rather than a record shaped by hand. The literal
    comes from `elm_json_literal` for the reason its own doc comment gives: a
    fixture that never arrived reads exactly like a rule that answered nothing.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, elm_json_literal(tree_with(children)))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def bot_source():
    return source_of(GAS_HUFFER_BOT_ELM)


def without_line_comments(text):
    """`--` comment lines dropped, so a comment cannot satisfy a code check.

    Only lines whose *first* non-space characters are `--`, which is what
    `elm-format` produces for a comment on its own line. A `--` inside a string
    literal is always mid-line here, so it survives -- which matters, since
    several of the decision lines these cases read carry one.
    """
    return "\n".join(line for line in text.split("\n")
                     if not line.strip().startswith("--"))


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", without_line_comments(text))


def top_level_declarations(source):
    """Every top-level declaration, as {name: body}, without its doc comment.

    `elm-format` puts exactly two blank lines between top-level declarations, so
    the split is structural rather than a guess, and it carries a body that is
    one long record or list literal whole -- `parseBotSettings` is exactly that
    shape, and the readers this repo reached for first stopped at a blank line
    or at a record's opening brace, which cost PRs #147, #156 and #159 an
    assertion that passed having read nothing. The file is validated against
    `elm-format` in the same change, so the premise cannot drift.

    The doc comment is dropped rather than kept, because these cases ask which
    declarations *read* something: a doc comment naming a field would answer yes
    for every declaration that merely explains it.
    """
    found = {}
    for chunk in source.split("\n\n\n"):
        body = re.sub(r"^\{-.*?-\}\n", "", chunk, flags=re.DOTALL)
        match = re.match(r"^([a-zA-Z][a-zA-Z0-9_]*) :", body)
        if match is not None:
            found[match.group(1)] = body
    return found


def block(name):
    """One top-level declaration, or a failure naming what was looked for.

    A missing name must never read as "nothing matched": that is the shape that
    makes a structural case pass having checked nothing.
    """
    blocks = top_level_declarations(bot_source())
    if name not in blocks:
        raise AssertionError("no top-level declaration named " + name)
    return blocks[name]


def elm_string(value):
    return json.dumps(value)


BULLET_LINE = re.compile(r"^\s*\+\s+(.*)$")
KEY_IN_BACKTICKS = re.compile(r"`([a-z][a-z0-9-]*)`")


def settings_section(header):
    """The `## Configuration Settings` bullets, and nothing else.

    Bounded at the sentence `bot_help.settings_section` stops at, so the
    header's own example block and the setup bullets above are outside it --
    the setup bullets carry no colon and would otherwise swallow the rest of
    the header into one bullet head.
    """
    after = header.split("## Configuration Settings", 1)[1]
    return after.split("When using more than one setting", 1)[0]


def documented_keys(header):
    """Every key the settings bullets *offer*, in order, without repeats.

    Only a bullet's head -- the part before its first colon -- is read, because
    a bullet's body names other settings in prose and demanding those be
    parseable keys would go red on a header that is telling the truth. The head
    is joined across physical lines, since one can span two.
    """
    keys = []
    item = None
    for line in settings_section(header).split("\n"):
        bullet = BULLET_LINE.match(line)
        if bullet is not None:
            if item is not None:
                keys.extend(KEY_IN_BACKTICKS.findall(item.split(":", 1)[0]))
            item = bullet.group(1)
        elif item is not None:
            if not line.strip() or ":" in item:
                keys.extend(KEY_IN_BACKTICKS.findall(item.split(":", 1)[0]))
                item = None
            else:
                item = item + " " + line.strip()
    if item is not None:
        keys.extend(KEY_IN_BACKTICKS.findall(item.split(":", 1)[0]))
    return list(dict.fromkeys(keys))


class GasHufferRepl(ElmRepl):
    """The shared harness, pointed at the gas huffer."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-repl-")
        kwargs.setdefault("app_dir", GAS_HUFFER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    def parses(self, settings_strings):
        """Whether each settings string is accepted at all."""
        return self.booleans([
            "parseBotSettings %s |> Result.map (always True) "
            "|> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])

    def rejection_reasons(self, settings_strings):
        """The error each settings string is rejected with, or `<accepted>`.

        `Result.Extra.merge` rather than a `case`, because a multi-line `case`
        inside a list does not survive the repl's own entry shape.
        """
        return self.strings([
            'parseBotSettings %s |> Result.map (always "<accepted>") '
            "|> Result.Extra.merge" % elm_string(settings)
            for settings in settings_strings])


def repl():
    return open_repl(GasHufferRepl)


class TheParserRefusesANameThatIsNotOneTest(unittest.TestCase):
    """The empty value, executed through the real parser.

    Two of these five would be dangerous unguarded and three would merely be
    useless, and the guard does not distinguish -- which is the point. An empty
    value has two established meanings in this codebase (`nonEmptySettingValue`
    reads it as unset, `splitSettingIntoNames` drops it as a trailing comma) and
    neither can apply where the whole assigned value is empty, because nothing
    is left to read the intent from.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_empty_value_is_rejected_for_every_setting_that_names_one_thing(self):
        # The whole point of the guard, and the case a mutation removing any one
        # guard has to fail. Asserted per setting rather than over the set, so
        # the failure names which one lost it.
        for key in NAME_SETTINGS:
            with self.subTest(key):
                self.assertEqual(self.repl.parses(["%s=" % key]), [False])

    def test_a_whitespace_only_value_is_rejected_too(self):
        # End to end, which is what an operator types. Note this alone does not
        # pin the guard: `parseSimpleListOfAssignments` trims every assigned
        # value before any handler sees it, so a guard with no trim of its own
        # passes this. The case below is the one that bites.
        for key in NAME_SETTINGS:
            with self.subTest(key):
                self.assertEqual(
                    self.repl.parses(["%s=   " % key, "%s=\t" % key]),
                    [False, False])

    def test_the_guard_judges_the_trimmed_value_itself(self):
        """The helper asked directly, because the framework hides this.

        #113 found this by mutation: taking `String.trim` out of
        `valueTypeNonEmptyString` left every end-to-end case green, since the
        caller had already trimmed. A guard that works only because its current
        caller trims is a guard whose next caller does not.
        """
        answers = self.repl.strings([
            'valueTypeNonEmptyString (\\_ settings -> settings) %s '
            '|> Result.map (always "<accepted>") |> Result.Extra.merge'
            % elm_string(value)
            for value in ["", "   ", "\t", " " + FICTIONAL_TAG + " "]])
        self.assertEqual(answers[:3], [answers[0], answers[0], answers[0]])
        self.assertIn("nothing", answers[0])
        self.assertEqual(answers[3], "<accepted>")

    def test_the_rejection_says_which_setting_and_why(self):
        # The framework prepends the setting's name; the value carries the
        # reason and the fix. A rejection an operator cannot act on is a run
        # that ends with a shrug.
        for key in NAME_SETTINGS:
            with self.subTest(key):
                reason = self.repl.rejection_reasons(["%s=" % key])[0]
                self.assertIn(key, reason)
                self.assertIn("Delete the line", reason)

    def test_the_guard_stores_the_name_with_its_surrounding_space_gone(self):
        # The same trim in its other direction: the stored value is what the
        # status line quotes back and what a later matcher compares against.
        self.assertEqual(
            self.repl.strings([
                'parseBotSettings %s |> Result.map (.homeStructureName '
                '>> Maybe.withDefault "<unset>") |> Result.withDefault '
                '"<rejected>"'
                % elm_string("home-structure-name=  %s  " % FICTIONAL_STRUCTURE)]),
            [FICTIONAL_STRUCTURE])

    def test_an_empty_integer_setting_is_refused_by_the_framework(self):
        # Not this file's guard -- `String.toInt ""` is `Nothing` and
        # `AppSettings.valueTypeInteger` answers `Err`. Asserted so that a later
        # change moving one of these onto a string type has to notice it is
        # giving up a refusal it currently gets for free.
        for key in INTEGER_SETTINGS:
            with self.subTest(key):
                self.assertEqual(self.repl.parses(["%s=" % key]), [False])

    def test_a_settings_string_naming_everything_parses(self):
        # The positive control. Without it every case above is satisfied by a
        # parser that refuses everything.
        settings = "\n".join([
            "anomaly-group = Gas Site",
            "gas-cloud-name-prefix = Fullerite-",
            "home-structure-name = " + FICTIONAL_STRUCTURE,
            "retreat-bookmark-prefix = *",
            "friendly-ship-tag = " + FICTIONAL_TAG,
            "dscan-interval-seconds = 5",
            "bot-step-delay = 499",
        ])
        self.assertEqual(self.repl.parses([settings]), [True])

    def test_the_launcher_passes_no_settings_of_its_own(self):
        """#456's rule, checked against the launcher rather than remembered.

        Nothing identifying may be committed, so `run_gas_huffer.sh` follows
        `run_autopilot.sh` rather than `run_mission.sh`: no `SETTINGS=` variable
        and no `--settings` of its own. An operator's own `--settings` still
        reaches the host through `"$@"`.
        """
        source = source_of(RUN_GAS_HUFFER)
        # The *last* occurrence: the header comment names the host too, and
        # splitting at the first one would read the whole script as the command.
        command = source.rsplit("botlab_host.py", 1)[1]
        self.assertNotIn("--settings", command)
        self.assertNotIn("--defaults", source)
        self.assertIsNone(re.search(r'^SETTINGS=', source, re.MULTILINE))
        self.assertIn('"$@"', command)


class TheUnsetTagTrustsNobodyTest(unittest.TestCase):
    """The fail-closed direction, executed rather than asserted in prose.

    Wrong in the direction this refuses, the bot keeps harvesting beside a ship
    it has never seen before -- and the failure is silent, because "nothing
    hostile on grid" is what the status line prints either way. Wrong in the
    other direction it leaves a site it could have kept working, which costs a
    warp.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def trust_from(self, settings):
        return ("(parseBotSettings %s |> Result.map hostileTrustFromSettings "
                "|> Result.withDefault TrustNobody)" % elm_string(settings))

    def test_with_no_tag_every_ship_reads_hostile(self):
        # The case a permissive default has to fail. Asked of several names
        # including the empty one, so a rule that happened to answer `False` for
        # one string cannot pass.
        answers = self.repl.evaluate([
            "shipReadsFriendly %s %s" % (self.trust_from(""),
                                         elm_string(name))
            for name in SHIP_NAMES])
        self.assertEqual(answers, [False] * len(SHIP_NAMES))

    def test_the_default_settings_name_no_friendly_tag(self):
        # The other end of the same property: the default is `Nothing` rather
        # than a value that happens to match nothing today.
        self.assertEqual(
            self.repl.evaluate([
                "defaultBotSettings.friendlyShipTag == Nothing",
                "hostileTrustFromSettings defaultBotSettings == TrustNobody",
            ]),
            [True, True])

    def test_a_configured_tag_is_matched_as_a_substring_ignoring_case(self):
        # The positive control, without which every case above is satisfied by a
        # rule that answers `False` for everything.
        trust = self.trust_from("friendly-ship-tag = " + FICTIONAL_TAG)
        answers = self.repl.evaluate([
            "shipReadsFriendly %s %s" % (trust, elm_string(name))
            for name in [
                FICTIONAL_TAG + " Somebody",
                "Somebody " + FICTIONAL_TAG.lower(),
                "Somebody Else",
                "",
            ]])
        self.assertEqual(answers, [True, True, False, False])

    def test_an_empty_tag_can_never_reach_the_permissive_branch(self):
        """The guard and the default are one property, not two.

        `TrustShipsTagged ""` would match every ship there is, which is the
        fail-closed direction inverted by a missing keystroke rather than by a
        changed default. The parser is what stops it, so the two cases have to
        be read together: this asks the parser, and asserts what the rule would
        have done had one got through.
        """
        self.assertEqual(self.repl.parses(["friendly-ship-tag="]), [False])
        self.assertEqual(
            self.repl.evaluate([
                'shipReadsFriendly (TrustShipsTagged "") '
                + elm_string("Somebody Else")]),
            [True])

    def test_the_clause_says_which_way_round_it_is(self):
        # An operator watching a run has to be able to tell the two postures
        # apart, and the unset one has to say what it means rather than only
        # that nothing is set.
        unset, configured = self.repl.strings([
            "describeHostileTrust %s" % self.trust_from(""),
            "describeHostileTrust %s" % self.trust_from(
                "friendly-ship-tag = " + FICTIONAL_TAG),
        ])
        self.assertIn("every ship reads hostile", unset)
        self.assertIn("friendly-ship-tag", unset)
        self.assertIn(FICTIONAL_TAG, configured)
        self.assertIn("every other ship reads hostile", configured)

    def test_nothing_but_the_status_line_reads_the_trust_rule(self):
        """`quickMessage`'s posture (#130), pinned while it is still true.

        The rule exists for #462 to plug into. Until then it is an instrument,
        and a case here is what makes a decision starting to consult it a
        decision somebody argues for rather than one that drifts in.
        """
        source = bot_source()
        readers = [name for name, text in top_level_declarations(source).items()
                   if "shipReadsFriendly" in collapsed(text)
                   and name != "shipReadsFriendly"]
        self.assertEqual(readers, [], readers)


class TheSetupListPutsThePauseMenuFirstTest(unittest.TestCase):
    """`closeSystemSettingsMenu` above everything, and reachable.

    The ordering is what makes the message box's Escape rung safe: that key can
    open the client's own pause menu, and this list answers with its head, so a
    menu opened on one reading is closed on the next by the branch that exists
    for it -- before anything else is tried.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_pause_menu_is_the_first_entry_and_the_list_answers_with_its_head(self):
        body = collapsed(block("generalSetupInUserInterface"))
        entries = re.search(r"\[ (.*?) \] \|> List\.filterMap", body)
        self.assertIsNotNone(body)
        self.assertIsNotNone(entries, body)
        names = [entry.strip().split()[0]
                 for entry in entries.group(1).split(" , ")]
        self.assertEqual(names[0], "closeSystemSettingsMenu", names)
        self.assertIn("closeMessageBox", names)
        self.assertLess(names.index("closeSystemSettingsMenu"),
                        names.index("closeMessageBox"), names)
        self.assertIn("|> List.head", body)

    def test_the_setup_list_is_asked_before_anything_that_flies_the_ship(self):
        root = collapsed(block("gasHufferDecisionRootBeforeApplyingSettings"))
        self.assertLess(root.index("generalSetupInUserInterface"),
                        root.index("branchDependingOnDockedOrInSpace"), root)

    def test_the_pause_menu_branch_fires_on_the_menu_the_client_draws(self):
        """Reachability, which a placement case cannot see.

        #15, #34 and #42 all shipped guards that were correctly placed and could
        never be true in the state they ran in. So the branch is asked about a
        real parsed tree carrying the layer and the button it navigates by, and
        about one without them as the control.
        """
        answers = self.repl.evaluate(
            ["Maybe.map (closeSystemSettingsMenu >> (/=) Nothing) menuIsOpen"
             " |> Maybe.withDefault False",
             "Maybe.map (closeSystemSettingsMenu >> (==) Nothing) noMenu"
             " |> Maybe.withDefault False",
             # Without this the two above are satisfied by fixtures that never
             # decoded, since `Maybe.withDefault False` hides that.
             "menuIsOpen /= Nothing",
             "noMenu /= Nothing"],
            definitions=[reading_binding("menuIsOpen", [system_menu_layer()]),
                         reading_binding("noMenu", [ordinary_layer()])])
        self.assertEqual(answers, [True, True, True, True])


class TheMessageBoxLadderIsPortedWholeTest(unittest.TestCase):
    """#101 / #138's ladder: answer, Escape, then stand aside.

    This list is evaluated above the docked-or-in-space split, so anything in it
    that can repeat forever freezes the whole bot rather than one branch. The
    ladder is what bounds the one known way that happens.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_three_rungs_are_reached_in_order(self):
        answers = self.repl.evaluate([
            "messageBoxStandoffVerdict Nothing == AnswerTheMessageBox",
            'messageBoxStandoffVerdict (Just { identity = "x", readings = 1 })'
            " == AnswerTheMessageBox",
            'messageBoxStandoffVerdict (Just { identity = "x", readings = '
            "messageBoxAnswersBeforeEscape - 1 }) == AnswerTheMessageBox",
            'messageBoxStandoffVerdict (Just { identity = "x", readings = '
            "messageBoxAnswersBeforeEscape }) == PressEscapeAtTheMessageBox",
            'messageBoxStandoffVerdict (Just { identity = "x", readings = '
            "messageBoxStandoffGiveUpReadings - 1 })"
            " == PressEscapeAtTheMessageBox",
            'messageBoxStandoffVerdict (Just { identity = "x", readings = '
            "messageBoxStandoffGiveUpReadings }) == LeaveTheMessageBoxAlone",
            # A fixed value past the bound, beside the boundary pair: a case
            # asking only about `constant - 1` and `constant` passes for any
            # constant, including one that admits everything.
            'messageBoxStandoffVerdict (Just { identity = "x", readings = 5000'
            " }) == LeaveTheMessageBoxAlone",
        ])
        self.assertEqual(answers, [True] * 7)

    def test_the_give_up_bound_is_written_as_a_multiple(self):
        # So the argument -- Escape gets exactly as long as the answer it
        # replaced -- cannot drift away from the number.
        self.assertIn("messageBoxAnswersBeforeEscape * 2",
                      collapsed(block("messageBoxStandoffGiveUpReadings")))

    def test_the_count_is_about_this_box_and_resets_on_a_different_one(self):
        answers = self.repl.values([
            'messageBoxStandoffAfterReading { before = Nothing, identityNow ='
            ' Just "a" } |> Maybe.map .readings',
            'messageBoxStandoffAfterReading { before = Just { identity = "a",'
            ' readings = 7 }, identityNow = Just "a" } |> Maybe.map .readings',
            'messageBoxStandoffAfterReading { before = Just { identity = "a",'
            ' readings = 7 }, identityNow = Just "b" } |> Maybe.map .readings',
            'messageBoxStandoffAfterReading { before = Just { identity = "a",'
            " readings = 7 }, identityNow = Nothing } |> Maybe.map .readings",
        ], r"(Just \d+|Nothing) : Maybe Int")
        self.assertEqual(answers,
                         ["Just 1", "Just 8", "Just 1", "Nothing"])

    def test_the_give_up_hands_the_tree_back_rather_than_raising_an_alarm(self):
        # `Nothing` from `closeMessageBox` is the whole of the ladder: the box
        # stays on the screen and every branch below now works around it, which
        # is worse than a closed box and incomparably better than nothing in the
        # bot running at all.
        body = collapsed(block("closeMessageBox"))
        self.assertIn("LeaveTheMessageBoxAlone -> Nothing", body)
        self.assertNotIn("askForHelpToGetUnstuck", body)

    def test_the_automatic_answer_carries_no_affirmative(self):
        # #54's standing rule. These dialogs guard destructive actions, so the
        # bot's automatic reply is always the one that declines.
        body = collapsed(block("closeMessageBoxByDeclining"))
        self.assertIn("no_dialog_button", body)
        self.assertNotIn("yes_dialog_button", body)
        self.assertNotIn('"yes"', body.lower())

    def test_the_connection_lost_box_is_left_alone_outright(self):
        # Its only control quits the client, so both the declining answer and
        # the Escape rung are destructive. Matched on two of the client's own
        # words rather than one, since a single common word would silence
        # dialogs this must not silence.
        body = collapsed(block("messageBoxSaysTheConnectionIsLost"))
        self.assertIn('"connection lost"', body)
        self.assertIn('"connection to server was lost"', body)
        self.assertIn("&&", body)


class TheRetreatCoverSaysWhenNothingIsArmedTest(unittest.TestCase):
    """`attritionIsUnguarded`'s posture, adapted.

    That rule exists because the mission runner's damage-window guard cannot see
    a ship being ground down. The same shape is worse here: this hull's survival
    plan is to leave rather than to tank it, so a retreat that is not armed is
    no plan at all rather than a weaker one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def cover(self, detection="False", home="Nothing", prefix='"*"'):
        return ("{ hostileDetectionIsArmed = %s, homeStructureName = %s"
                ", retreatBookmarkPrefix = %s }" % (detection, home, prefix))

    def test_both_halves_have_to_hold_for_the_retreat_to_read_as_armed(self):
        answers = self.repl.evaluate([
            "retreatIsUnarmed " + self.cover(),
            "retreatIsUnarmed " + self.cover(detection="True"),
            "retreatIsUnarmed " + self.cover(
                home='Just "%s"' % FICTIONAL_STRUCTURE),
            "retreatIsUnarmed " + self.cover(
                detection="True", home='Just "%s"' % FICTIONAL_STRUCTURE),
        ])
        self.assertEqual(answers, [True, True, True, False])

    def test_it_fires_today_because_nothing_detects_a_hostile_yet(self):
        """Reachability, said as the state the code actually runs in.

        `hostileDetectionIsArmed` is `False` at its one call site because
        nothing in this app reads the Directional Scanner or classifies an
        overview row. So this clause fires on every reading of every run, which
        is exactly what it should do while that is true, and #462 is what flips
        it.
        """
        body = collapsed(block("retreatCoverFromContext"))
        self.assertIn("hostileDetectionIsArmed = False", body)

    def test_the_clause_names_which_half_is_missing(self):
        unarmed, no_home, armed = self.repl.strings([
            "describeRetreatCover " + self.cover(),
            "describeRetreatCover " + self.cover(detection="True"),
            "describeRetreatCover " + self.cover(
                detection="True", home='Just "%s"' % FICTIONAL_STRUCTURE),
        ])
        self.assertIn("RETREAT NOT ARMED", unarmed)
        self.assertIn("notices a hostile", unarmed)
        self.assertIn("RETREAT NOT ARMED", no_home)
        self.assertNotIn("notices a hostile", no_home)
        self.assertIn("home-structure-name", no_home)
        self.assertNotIn("RETREAT NOT ARMED", armed)
        self.assertIn(FICTIONAL_STRUCTURE, armed)

    def test_nothing_decides_on_it(self):
        source = bot_source()
        readers = [name for name, text in top_level_declarations(source).items()
                   if "retreatIsUnarmed" in collapsed(text)
                   and name not in ("retreatIsUnarmed", "describeRetreatCover")]
        self.assertEqual(readers, [], readers)


class TheSessionEndingBoundHasNowhereToGoYetTest(unittest.TestCase):
    """The deferral marker for #102 / #133, recorded rather than assumed.

    Both of those issues are one defect: a bound counted in
    `updateMemoryForNewReadingFromGame` on every reading, and compared inside a
    branch the tree reaches on a fraction of them. The fix is placement -- the
    comparison is asked from the head of the decision root, where nothing can
    decline to ask it.

    This app has no such bound, so there is nothing to place. What it has
    instead is a doc comment saying so and naming the shape, and this case,
    which goes red the day something here ends a session -- so whoever writes
    #463's give-up has to decide where it is asked rather than inheriting the
    answer by default.
    """

    def test_nothing_here_ends_a_session_yet(self):
        # Over the declaration *bodies*, with their doc comments stripped: the
        # whole source carries `InternalFinishSession` in prose, explaining what
        # a rejected setting costs, and a case that read that as code would be
        # red from the day it was written.
        bodies = " ".join(collapsed(text) for text
                          in top_level_declarations(bot_source()).values())
        self.assertNotIn("FinishSession", bodies)

    def test_the_root_names_the_shape_a_future_bound_has_to_take(self):
        # Collapsed, because `elm-format` owns where these lines break and a
        # phrase this reads for is one wrap away from being unfindable.
        doc = collapsed(bot_source().split(
            "gasHufferDecisionRootBeforeApplyingSettings :", 1)[0]
            .rsplit("{-|", 1)[1])
        self.assertIn("endSessionOnAnExpiredBound", doc)
        self.assertIn("#102", doc)
        self.assertIn("#133", doc)
        self.assertIn("bounds elapsed time", doc)


class TheScaffoldSaysItIsAScaffoldTest(unittest.TestCase):
    """A branch that does nothing and reports nothing is indistinguishable from
    one that is stuck.

    That is `/review-silent-success` exactly, and it is the one thing about a
    scaffold that can go wrong before any behaviour exists: an operator starting
    this bot has to be told it is not going to harvest, on every reading, rather
    than watching a decision log that looks like a bot thinking.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_branches_name_themselves_and_the_issue_that_fills_them(self):
        docked, in_space = self.repl.strings(
            ["nothingToDoDockedYet", "nothingToDoInSpaceYet"])
        for text in (docked, in_space):
            self.assertIn("on purpose", text)
            self.assertIn("#46", text)
        self.assertIn("#464", docked)
        self.assertIn("#461", in_space)

    def test_the_status_line_opens_by_saying_so(self):
        body = collapsed(block("statusTextFromState"))
        self.assertIn("SCAFFOLD ONLY", body)

    def test_the_header_says_it_before_the_settings_an_operator_would_read(self):
        header = bot_source().split("\n-}", 1)[0]
        self.assertIn("SCAFFOLD ONLY", header)
        self.assertLess(header.index("SCAFFOLD ONLY"),
                        header.index("## Configuration Settings"))


class TheClientSetupContractIsInTheHeaderTest(unittest.TestCase):
    """What `bot_help.py` prints, and what the bot cannot enforce for itself.

    Three of these cannot be checked from inside a reading, so the header is the
    only place they can be stated -- and the orbit distance is the one with no
    reading at all behind it, since the Selected Item panel's Orbit button
    orbits at whatever range the client last used.
    """

    def setUp(self):
        self.header = bot_source().split("\n-}", 1)[0]

    def test_the_orbit_distance_is_named_as_a_client_setup_requirement(self):
        # The instruction itself, not merely the words somewhere in the header:
        # a mutation that removed the bullet and left the paragraph under it
        # passed the looser form of this case.
        self.assertIn(
            "**Set the Orbit button's distance by hand, once, before starting"
            " a run.**", self.header)
        # And the client's own refusal, which is the only thing that will ever
        # tell the bot the setup is wrong -- there is no reading that says what
        # range the button remembers.
        self.assertIn("mining range", self.header)

    def test_the_probe_scanner_group_column_is_required(self):
        self.assertIn("probe scanner window must be open", self.header)
        self.assertIn("`Group` column", self.header)

    def test_the_overview_columns_are_required(self):
        self.assertIn("overview must show gas clouds", self.header)
        self.assertIn("Name column", self.header)
        self.assertIn("Type column", self.header)

    def test_the_module_rows_are_named(self):
        self.assertIn("gas harvesters in the **top** row", self.header)
        self.assertIn("propulsion module **first in the middle row**",
                      self.header)

    def test_the_header_carries_the_terminator_bot_help_stops_at(self):
        """`bot_help.settings_section` ends at this sentence.

        Every other app's header carries it, and
        `test_settings_section_bounded_at_header_close` asserts that over the
        whole tree -- so an app without it would make that case's own premise
        false rather than merely printing more.
        """
        after_heading = self.header.split("## Configuration Settings", 1)[1]
        self.assertIn("When using more than one setting", after_heading)

    def test_every_documented_key_is_one_the_parser_accepts(self):
        """The cross-app rule (#161) asked of this app on its own.

        `test_documented_settings_are_parsed` states it over every app, so this
        is redundant by design -- and it is here anyway, because a scaffold is
        exactly where a header bullet gets written for a setting nobody wired,
        and this file is where somebody adding one would look.

        Asserted as an **equality** in both directions rather than as "every
        registered key is documented". That one-way form is what survived a
        mutation adding `avoid-rat` to the header: a key the parser refuses,
        offered to an operator whose settings string then ends the session at
        startup, which is #161's own shape.
        """
        registered = set(re.findall(r'\(\s*"([a-z][a-z0-9-]*)"\s*,',
                                    block("parseBotSettings")))
        self.assertEqual(
            registered,
            set(NAME_SETTINGS) | set(INTEGER_SETTINGS), registered)
        self.assertEqual(set(documented_keys(self.header)), registered,
                         documented_keys(self.header))

    def test_the_example_settings_string_uses_fictional_names_only(self):
        """#456's rule over the one place a real name would be easiest to leave.

        The header's fenced block is the text an operator pastes, and every key
        in it must be one the parser accepts -- which
        `test_documented_settings_are_parsed` asserts over every app. What this
        adds is that the *values* name nothing real.
        """
        fenced = re.search(r"```\n(.*?)```", self.header, re.DOTALL)
        self.assertIsNotNone(fenced, self.header)
        example = fenced.group(1)
        self.assertIn(FICTIONAL_STRUCTURE, example)
        self.assertIn(FICTIONAL_TAG, example)


class TheLauncherAnswersHelpBeforeItKillsAnythingTest(unittest.TestCase):
    """Asking what the settings are must not end a session in progress.

    Every launcher here has that property and it is easy to lose by adding a
    preflight above the `--help` arm, which is why it is read out of the script
    by position rather than assumed.
    """

    def setUp(self):
        self.source = source_of(RUN_GAS_HUFFER)

    def test_help_is_answered_above_the_guard_and_the_preflight(self):
        help_at = self.source.index("bot_help.py")
        self.assertLess(help_at, self.source.index("build_tools.sh"))
        self.assertLess(help_at, self.source.index("pgrep -f"))
        # The invocation rather than the header's mention of it.
        self.assertLess(help_at, self.source.rindex("botlab_host.py"))
        # And it leaves before any of that, rather than merely being printed
        # first: a `--help` that fell through would still kill a session.
        self.assertLess(self.source.index("bot_help.py"),
                        self.source.index("exit 0"))
        self.assertLess(self.source.index("exit 0"),
                        self.source.index("build_tools.sh"))

    def test_the_guard_never_prints_the_clients_command_line(self):
        # `pgrep -f` matches the command line without printing it; `-l` would
        # dump the account's `/ssoToken=` and `/refreshToken=` into the log.
        self.assertIn("pgrep -f ", self.source)
        self.assertNotIn("pgrep -fl", self.source)
        self.assertNotIn("ps aux", self.source)

    def test_the_guard_kills_every_other_launcher_too(self):
        # Two bots fighting over the cursor is chaos, and a launcher that only
        # knows about itself leaves the other one running.
        for pattern in ("run_gas_huffer", "run_mission", "run_saxrat",
                        "run_autopilot", "botlab_host.py"):
            with self.subTest(pattern):
                self.assertIn(pattern, self.source)

    def test_it_drives_real_input_and_says_so(self):
        self.assertIn("--execute-input", self.source)
        self.assertIn("WILL click and type for real", self.source)


class EveryVendoredModuleIsSomebodyElsesTest(unittest.TestCase):
    """Every vendored module is byte-identical to a maintained copy, named.

    None of these files is this app's to edit. Being byte-identical to
    somebody's is what makes re-syncing mechanical rather than a note somebody
    has to remember: a shared fix that lands in the named app and not here goes
    red *here*, naming the file, rather than being discovered by whatever breaks
    next.

    **The parser is deliberately not saxrat's, and that is the one interesting
    row.** Vendoring saxrat's whole tree was the first attempt and CI caught it:
    `test_saxrat_opportunity_tracker_button.TheVendoredParserPolicyIsUnbroken`
    asserts `parseOpportunityInfoPanelEntriesFromUITreeRoot` exists in saxrat's
    copy and nowhere else -- PR #252's policy that an app-local *panel* parser
    lands in one copy -- and vendoring byte for byte inherited it, so two copies
    had it.

    That case's own sibling shows when inheriting anyway is right: the mission
    block travels with the *variant* rather than the app, and the haulerbot
    carries it because it genuinely needs `stripHtmlTags` and `ShipItemCard` to
    compile. **This app needs none of the tracker**, so inheriting it would be
    gratuitous where the haulerbot's was forced, and relaxing a real property to
    avoid a copy that already exists is the wrong trade.

    So the rule this settles on, which a later app can reuse: **take the least
    diverged copy that compiles this app's `Bot.elm`.** The parser has four
    variants -- the plain baseline (`warp-to-0-autopilot`, byte-identical to
    `combat-anomaly-bot`), that plus `getElementIdFromDictEntries` (wingman),
    saxrat's, and the mission runner's (shared with the haulerbot). The plain
    baseline will not do, and `test_the_least_diverged_copy_still_had_to_carry_
    something` is why: `closeSystemSettingsMenu` navigates by `_elementId` to
    reach the pause menu's close button, which is exactly the helper wingman's
    copy adds and nothing else. Everything #460-#464 will read -- the probe
    scanner's `cellsTexts`, the Directional Scanner, the capacity gauge, the
    Locations window, the overview, the module buttons, the synthetic host
    nodes -- is already in it. The one thing absent is
    `parseTargetHitpointsPercent`, an instrument for a combat target's health
    ring, and this bot locks a gas cloud rather than a ship.

    Everything else stays saxrat's, because `Bot.elm` is written against
    saxrat's framework and settings modules -- wingman is on `PromptParser` and
    vendors no `Common/AppSettings.elm` at all, so its tree could not host a
    `parseBotSettings` of the shape #459 asks for.

    **No parser count is written down here**, for `vendored_parser_count`'s own
    reason: a hardcoded `6` in seven cases all went red the day a new bot was
    added, which is exactly the situation this app creates.

    **The merge hazard is the same mechanism.** Two parser changes are in flight
    -- #457 / PR #466 (`parseLocationsWindowFromUITreeRoot` matching
    `StandaloneBookmarkWnd` as well as `LocationsWindow`) and #458 (a
    `parseDirectionalScanResult`). This copy carries neither. Both are parses of
    *the client's own widgets* rather than of one app's panel, so by the same
    policy they belong in every copy; whichever change merges last re-syncs, and
    the row below is what says so.
    """

    # Each vendored file, and the app whose copy it must equal byte for byte.
    VENDORED = {
        os.path.join("EveOnline", "ParseUserInterface.elm"): "eve-online-wingman",
        os.path.join("EveOnline", "BotFramework.elm"): "eve-online-saxrat",
        os.path.join("EveOnline", "BotFrameworkSeparatingMemory.elm"): "eve-online-saxrat",
        os.path.join("EveOnline", "MemoryReading.elm"): "eve-online-saxrat",
        os.path.join("Common", "AppSettings.elm"): "eve-online-saxrat",
        os.path.join("Common", "EffectOnWindow.elm"): "eve-online-saxrat",
        os.path.join("Common", "DecisionPath.elm"): "eve-online-saxrat",
        "elm.json": "eve-online-saxrat",
    }

    def test_every_vendored_module_matches_its_named_copy_byte_for_byte(self):
        for relative, app in self.VENDORED.items():
            with self.subTest(relative):
                self.assertEqual(
                    source_of(os.path.join(GAS_HUFFER_DIR, relative)),
                    source_of(os.path.join(APPLICATIONS_DIR, app, relative)),
                    "%s must be %s's copy byte for byte" % (relative, app))

    def test_no_app_local_panel_parser_is_inherited(self):
        """The other half of the row above, and the one CI caught.

        Byte-identity to wingman's copy already implies this, but only while
        wingman's copy stays clean. Naming the declarations is what makes a
        lazy re-sync from the wrong app fail *here* as well as in the case that
        owns each of them, so whoever does it is told which app they took.
        """
        parser = source_of(os.path.join(
            GAS_HUFFER_DIR, "EveOnline", "ParseUserInterface.elm"))
        for declaration in ("parseOpportunityInfoPanelEntriesFromUITreeRoot",
                            "parseAgentMissionInfoPanelEntriesFromUITreeRoot",
                            "parseShipItemCardsFromUITreeRoot"):
            with self.subTest(declaration):
                self.assertNotIn(declaration, parser)

    def test_the_least_diverged_copy_still_had_to_carry_something(self):
        """Why wingman's copy and not the plain baseline, executed as a fact.

        `closeSystemSettingsMenu` reaches the pause menu's close button by
        `_elementId`, and `getElementIdFromDictEntries` is the whole of what
        wingman's copy adds to the baseline -- so this is not a preference
        between two equally good copies. The baseline is asserted to lack it, so
        a later change that "simplifies" this to the baseline fails here rather
        than at a compile error somebody reads as unrelated.
        """
        parser = source_of(os.path.join(
            GAS_HUFFER_DIR, "EveOnline", "ParseUserInterface.elm"))
        baseline = source_of(os.path.join(
            APPLICATIONS_DIR, "eve-online-warp-to-0-autopilot",
            "EveOnline", "ParseUserInterface.elm"))
        self.assertIn("getElementIdFromDictEntries :", parser)
        self.assertNotIn("getElementIdFromDictEntries :", baseline)
        self.assertIn("getElementIdFromDictEntries",
                      collapsed(block("closeSystemSettingsMenu")))

    def test_the_bot_is_on_the_one_host_interface_that_has_a_wrapper(self):
        # `test_host_interface_wrappers` asserts this over every app; a bot on
        # any other interface is refused by name rather than built against the
        # wrong wrapper.
        self.assertIn(
            "import BotLab.BotInterface_To_Host_2024_10_19 as InterfaceToHost",
            bot_source())


if __name__ == "__main__":
    unittest.main()
