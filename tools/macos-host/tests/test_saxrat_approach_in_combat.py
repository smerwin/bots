"""Tests for saxrat's third combat manoeuvre: approach the target and stay on it.

Issue #386. `orbit-in-combat` holds transversal at a distance and `keep-at-range`
holds a distance on purpose, so neither of them does what a brawler fit needs --
webs, scramblers and short-range guns all want the ship *on top of* the rat.
`approach-in-combat` is the third `YesOrNo` beside them, mutually exclusive with
both.

**The mechanism is a double click on the overview row, and it is not a
keystroke.** This bot had a `Q`-chord approach and PR #243 deliberately removed
it: `cg_input` posts a key event without stamping flags on it, so a posted `Q`
carries whatever modifier state the session happens to hold, and with the Fn bit
set that is macOS Quick Note -- one recorded run took that branch 1,571 times
while Notes came to the front 241 times with nobody at the machine. PR #241 fixed
the mis-stamping and does **not** make the removal redundant: #241 stops the
keystroke being mis-stamped, and #243 stops the keystroke existing.
`test_saxrat_approach_by_double_click` carries that reasoning and pins the
`lockTargetFromOverviewEntry` half of it; this file is the same rule about the
combat manoeuvre, and `test_the_approach_presses_no_key_at_all` is what refuses a
chord coming back through this door.

**A dispatched click is not success.** `ManeuverApproach` is what confirms the
manoeuvre took, exactly as `ManeuverOrbit` confirms the orbit arm next door: the
rule answers `Just` -- keeps commanding -- on every reading the client has not
reported the manoeuvre on, and `Nothing` on the readings it has. Reading the
dispatch back instead would be this repo's signature failure, so
`test_a_dispatched_click_is_not_the_confirmation` folds a session in which the
click goes out and the client never answers, and requires the branch to go on
commanding.

**Continuous approach, and the cost is stated rather than hidden.** The issue
leaves open whether to stop inside some range. Approaching and staying is what
the setting means and what a web/scram fit wants, and it needs no distance --
which is the trap the other two carry. PILOT.md: `no bot setting carries an
engagement distance`, so `orbit-in-combat` and `keep-at-range` fall back on a
*client* default nobody can read back, which shipped at 7,500 m and was suicidal
on a hull whose guns reach tens of kilometres. What continuous approach costs is
zero transversal against anything that tracks, which is a question about the fit;
`test_the_doc_comment_states_the_cost_and_declines_a_range` pins that the source
says so, because a cost recorded only in a pull request is a cost nobody reads.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, for the reason CLAUDE.md's "How a change is verified here"
gives, and the ship UI and overview rows they are asked about come from the
**real** `EveOnline.ParseUserInterface` -- so what the branch is handed is what
the bot would have been handed. The wiring, which is not an expression, is read
out of the source through a reader sliced by **indentation**: `let_binding`
readers that stop at the next ` <name> = ` stop at a record literal instead, and
PRs #147, #156, #159 and #162 each paid for that once.

Confirmed by mutation, twelve of them, no survivors. Each is listed with the
first case that failed on it, having been run rather than reasoned about:

 1. **a dispatched click counting as success** -- the arm answering `Nothing`
    whatever the client reported, which is what "the click went out, so it
    worked" looks like once there is no other input to read --
    `test_a_dispatched_click_is_not_the_confirmation`, and six more;
 2. **the mutual exclusion dropped**, so approach fires beside orbit --
    `test_orbit_wins_over_the_two_below_it` and
    `test_exactly_one_manoeuvre_is_chosen_for_every_combination`;
 3. **the setting parsed and never read** (#125's shape, and #195's) -- the
    field, the default and the parser handler all left in place with no decision
    consulting it -- `test_the_setting_is_read_by_a_decision`;
 4. **a `Q` chord reintroduced** in the approach arm --
    `test_the_approach_presses_no_key_at_all`,
    `test_the_approach_arm_presses_no_key` and
    `test_no_effect_anywhere_in_saxrat_presses_q`;
 5. the double click swapped for a single one --
    `test_the_approach_dispatches_a_double_click`;
 6. the arm reading `ManeuverOrbit` rather than `ManeuverApproach` --
    `test_the_client_s_own_manoeuvre_is_what_stops_the_commanding`;
 7. `approach-in-combat` dropped from the parser --
    `test_the_setting_is_accepted_and_sets_the_field`;
 8. its default flipped to `Yes` -- `test_the_default_is_off`;
 9. approach placed ahead of orbit in the rule, which changes what a settings
    string setting both already does -- `test_orbit_wins_over_the_two_below_it`;
10. the align fall-back dropped, so a bot with no setting approaches --
    `test_no_setting_still_aligns`;
11. a range clause added to the arm, so the approach stops at a distance --
    `test_the_doc_comment_states_the_cost_and_declines_a_range`, and the seven
    behaviour cases beside it;
12. the dispatch site's `case` reverted to its own `if` chain, so the executable
    rule is no longer what decides -- `test_the_dispatch_asks_the_rule`.

Two of those are worth reading twice, because they are the ones a case could
most easily have missed. **The click-counts-as-success mutation is caught by the
behaviour cases and not by any source read**, which is why the arm is executed
rather than inspected. And **the parsed-never-read mutation is caught by a
source read and by nothing else** -- the repl cannot see a rule that is not
consulted -- which is why `without_the_write_only_blocks` cuts the three places
a setting is written before looking for the read: counting occurrences over the
whole file cannot separate them, since the parser handler alone names the field
three times.

Nothing here reads a live game client, a running bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, collapsed, label, node, source_of)
from test_saxrat_learned_lock_range import (
    ROW_PITCH, ROW_TOP, flying, overview_rows, row_center)

# A rat's row, as the client draws one. The name is one the recorded runs carry.
RAT = "Centii Minion"

# The client's own words for the manoeuvres, which is what `parseShipUIIndication`
# matches on -- not a code this file made up. Kept together so a case asking
# about one is visibly asking about the same vocabulary as its neighbours.
APPROACHING = "Approach"
ORBITING = "Orbit"
KEEPING_RANGE = "Range"


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n") + '"'


def settings_string(orbit=None, keep=None, approach=None):
    """A settings string naming only the manoeuvre settings a case is about."""
    lines = []
    for key, value in (("orbit-in-combat", orbit),
                       ("keep-at-range", keep),
                       ("approach-in-combat", approach)):
        if value is not None:
            lines.append("%s=%s" % (key, value))
    return "\n".join(lines)


def indented_block(source, name, indent):
    """One binding, sliced by **indentation** rather than by the next name.

    A reader that ends at the next ` <name> = ` stops at a record literal, so an
    assertion about anything past a binding's first brace passes having read
    nothing -- PRs #147, #156, #159 and #162 each paid for that once. This ends
    at the first later line indented no further than the binding's own name,
    which a record's fields are not.
    """
    start = source.index("\n" + indent + name + " ")
    lines = source[start + 1:].split("\n")
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and not line.startswith(indent + " ") \
                and not line.startswith(indent + "\t"):
            if not (line.startswith(indent) and line[len(indent):].startswith(
                    (")", "]", "}", ",", "|>", "in"))):
                break
        body.append(line)
    return "\n".join(body)


def declaration(source, name):
    """One top-level declaration, from its type annotation to the next one."""
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def doc_comment_of(source, name):
    """The `{-| ... -}` block immediately above a declaration's annotation.

    `declaration` starts at the annotation, so it never contains the doc
    comment -- a case asserting on one through it reads the empty string and
    passes for any wording at all, which is how this file's first run reported
    a cost the source did not state.
    """
    start = source.index("\n%s :" % name)
    closing = source.rindex("-}", 0, start)
    opening = source.rindex("{-|", 0, closing)
    return source[opening:closing + len("-}")]


def without_the_write_only_blocks(source):
    """`Bot.elm` with the three places a setting is *written* cut out.

    The record field, the default and the parser handler are what every setting
    has whether or not anything consults it, so what is left is where a read
    would have to be. Counting occurrences over the whole file cannot do this
    job: `parseBotSettings`' handler names the field three times on its own --
    the lambda's parameter, the update's field and the value -- so a rule that
    deleted the read still counts five and any threshold that admits a real
    setting admits a dead one too. That is `avoid-rat` exactly (#125), and #195
    is the same shape again.
    """
    remaining = source
    for block in (declaration(source, "defaultBotSettings"),
                  declaration(source, "parseBotSettings"),
                  type_alias(source, "BotSettings")):
        remaining = remaining.replace(block, "")
    return remaining


def type_alias(source, name):
    """One `type alias N = { ... }` block, ending at its closing brace."""
    start = source.index("\ntype alias %s =" % name)
    end = source.index("\n    }", start) + len("\n    }")
    return source[start:end]


class ApproachRepl(SaxratRepl):
    """saxrat's `Bot.elm`, plus what asking about one manoeuvre arm costs.

    `ensureShipIsApproaching` takes a `ShipUI` and an `OverviewWindowEntry`, both
    of which come out of a really parsed reading here rather than being written
    as records -- so the case cannot drift from what the parser would have
    produced. The bindings ride in the preamble, which `imports_and_bindings`
    folds into the one `let` that asks the question, so they cost the same single
    compile the imports do (#172).
    """

    BINDINGS = (
        # Since #414 the arm takes a whole `BotDecisionContext`. Every field of
        # it is either the shipped default (`defaultBotSettings`,
        # `initBotMemory`) or the emptiest value its type has, so nothing in
        # the fixture can decide an answer except the reading -- the
        # arrangement `test_saxrat_approach_by_double_click` already uses.
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
        "shipUIOf = \\parsed -> parsed |> Maybe.andThen .shipUI",
        "rowOf = \\parsed -> parsed"
        " |> Maybe.map (.overviewWindows >> List.concatMap .entries)"
        " |> Maybe.withDefault [] |> List.head",
        # The arm, asked about a really parsed reading. `Nothing` from either
        # half of the reading is reported as `NO READING` rather than as the
        # rule declining, so a fixture that never arrived cannot pass for a rule
        # that answered nothing -- #174's lesson, applied to a two-part input.
        "armFor = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " Maybe.map2 (ensureShipIsApproaching (context p))"
        " (shipUIOf parsed) (rowOf parsed))",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeFor = \\parsed ->\n"
        "    case armFor parsed of\n"
        "        Nothing ->\n"
        "            \"NO READING\"\n"
        "        Just Nothing ->\n"
        "            \"NOT COMMANDING\"\n"
        "        Just (Just armNode) ->\n"
        "            (unpack armNode |> Tuple.first |> String.join \" | \")",
        "effectsOfLeaf = \\leaf ->\n"
        "    case leaf of\n"
        "        EveOnline.BotFrameworkSeparatingMemory.ContinueSession continue ->\n"
        "            continue.effectsOnGameClient\n"
        "        EveOnline.BotFrameworkSeparatingMemory.FinishSession ->\n"
        "            []",
        "effectsFor = \\parsed ->\n"
        "    case armFor parsed of\n"
        "        Just (Just armNode) ->\n"
        "            (unpack armNode |> Tuple.second |> effectsOfLeaf)\n"
        "        _ ->\n"
        "            []",
        "isKeyEffect = \\effect ->\n"
        "    case effect of\n"
        "        EffectOnWindow.KeyDown _ ->\n"
        "            True\n"
        "        EffectOnWindow.KeyUp _ ->\n"
        "            True\n"
        "        _ ->\n"
        "            False",
        "keysIn = List.filter isKeyEffect",
        # The gesture the host collapses into `cg_input`'s `doubleclick`: two
        # press/release pairs with nothing between them, carrying the move.
        "doubleClickAt = \\x y ->"
        " [ EffectOnWindow.MouseMoveTo { x = x, y = y }"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft ]",
        # The manoeuvre rule over a settings record, so the three settings can be
        # varied without a settings string being parsed for every combination.
        "manoeuvreFor = \\orbit keep approach ->"
        " combatManoeuvreFromSettings"
        " { defaultBotSettings | orbitInCombat = orbit"
        " , keepAtRange = keep, approachInCombat = approach }",
        "yes = Common.AppSettings.Yes",
        "no = Common.AppSettings.No",
    )

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.AppSettings",
        "import Common.DecisionPath",
        "import Common.EffectOnWindow as EffectOnWindow",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import EveOnline.BotFrameworkSeparatingMemory",
        "import Result.Extra",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-approach-in-combat-")
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)

    @staticmethod
    def reading(name, maneuver=None, distance="5,000 m", targeted=True):
        """One really parsed reading: a ship UI plus one overview row."""
        return ApproachRepl.reading_binding(name, [
            flying(maneuver),
            overview_rows([(distance, RAT, "111", targeted)]),
        ])

    def parses(self, settings_strings):
        return self.evaluate([
            "parseBotSettings %s |> Result.map (always True)"
            " |> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])

    def field_after(self, settings_strings, field):
        """What one settings field reads after each string is parsed."""
        return self.strings([
            'parseBotSettings %s |> Result.map (.%s >> Debug.toString)'
            ' |> Result.Extra.merge' % (elm_string(settings), field)
            for settings in settings_strings])


class TheSettingIsParsedTest(unittest.TestCase):
    """`approach-in-combat`, executed through the real parser.

    A setting read out of the source proves the key is written down; only the
    parser proves it is accepted, and #161 is the app that documented one its
    parser did not know.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ApproachRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_setting_is_accepted_and_sets_the_field(self):
        self.assertEqual(
            self.repl.parses([
                settings_string(approach="yes"),
                settings_string(approach="no"),
            ]),
            [True, True])
        self.assertEqual(
            self.repl.field_after([
                settings_string(approach="yes"),
                settings_string(approach="no"),
            ], "approachInCombat"),
            ["Yes", "No"])

    def test_the_default_is_off(self):
        """An existing settings string is unchanged by this setting existing."""
        self.assertEqual(
            self.repl.field_after([""], "approachInCombat"), ["No"])

    def test_a_value_that_is_not_yes_or_no_is_refused(self):
        """`valueTypeYesOrNo`'s own answer, not something this setting invents.

        `BotFramework` answers a settings parse error with
        `InternalFinishSession`, so this ends a session rather than quietly
        leaving the manoeuvre at whatever the last legible line said.
        """
        self.assertEqual(
            self.repl.parses([settings_string(approach="sometimes")]),
            [False])

    def test_the_two_siblings_still_parse_beside_it(self):
        """The control: this file is about the third setting, not the parser."""
        answers = self.repl.field_after(
            [settings_string(orbit="yes"), settings_string(keep="yes")],
            "orbitInCombat")
        self.assertEqual(answers, ["Yes", "No"])
        self.assertEqual(
            self.repl.field_after(
                [settings_string(orbit="yes"), settings_string(keep="yes")],
                "keepAtRange"),
            ["No", "Yes"])

    def test_all_three_together_parse(self):
        """Setting all three is legal, and the rule below is what resolves it.

        A parser that refused the combination would be a second place the
        exclusion lives, and two places that can disagree about which manoeuvre
        is chosen is what this file exists to prevent.
        """
        self.assertEqual(
            self.repl.parses(
                [settings_string(orbit="yes", keep="yes", approach="yes")]),
            [True])


class TheThreeSettingsAreMutuallyExclusiveTest(unittest.TestCase):
    """`combatManoeuvreFromSettings`, over every combination of the three.

    Asked as four equalities per combination rather than one, so a rule that
    answered two things at once -- or none -- fails here rather than passing on
    whichever constructor a case happened to name.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ApproachRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    ALL = [(orbit, keep, approach)
           for orbit in (False, True)
           for keep in (False, True)
           for approach in (False, True)]

    @staticmethod
    def expected(orbit, keep, approach):
        if orbit:
            return "ManoeuvreOrbit"
        if keep:
            return "ManoeuvreKeepAtRange"
        if approach:
            return "ManoeuvreApproach"
        return "ManoeuvreAlign"

    def answers(self):
        def call(combination):
            return "manoeuvreFor %s" % " ".join(
                "yes" if flag else "no" for flag in combination)

        names = ["ManoeuvreOrbit", "ManoeuvreKeepAtRange",
                 "ManoeuvreApproach", "ManoeuvreAlign"]
        expressions = ["(%s) == %s" % (call(combination), name)
                       for combination in self.ALL for name in names]
        flat = self.repl.evaluate(expressions)
        return {combination: [name
                              for name, answer in zip(names, flat[index * 4:index * 4 + 4])
                              if answer]
                for index, combination in enumerate(self.ALL)}

    def test_exactly_one_manoeuvre_is_chosen_for_every_combination(self):
        for combination, chosen in self.answers().items():
            self.assertEqual(
                chosen, [self.expected(*combination)],
                "orbit=%s keep=%s approach=%s" % combination)

    def test_orbit_wins_over_the_two_below_it(self):
        """An existing settings string picks exactly what it picked before.

        `orbit-in-combat=yes` was the first arm of the chain this replaces, so a
        rule that put approach ahead of it would change what every settings
        string setting both already does.
        """
        answers = self.answers()
        self.assertEqual(answers[(True, False, True)], ["ManoeuvreOrbit"])
        self.assertEqual(answers[(True, True, True)], ["ManoeuvreOrbit"])
        self.assertEqual(answers[(False, True, True)],
                         ["ManoeuvreKeepAtRange"])

    def test_approach_is_chosen_when_it_is_the_only_one_set(self):
        self.assertEqual(
            self.answers()[(False, False, True)], ["ManoeuvreApproach"])

    def test_no_setting_still_aligns(self):
        """The fall-back saxrat has always had, unchanged."""
        self.assertEqual(
            self.answers()[(False, False, False)], ["ManoeuvreAlign"])


class TheApproachIsCommandedUntilTheClientAnswersTest(unittest.TestCase):
    """The arm itself, over readings the real parser produced."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ApproachRepl)
        cls.definitions = [
            ApproachRepl.reading("idle"),
            ApproachRepl.reading("approaching", APPROACHING),
            ApproachRepl.reading("orbiting", ORBITING),
            ApproachRepl.reading("keepingRange", KEEPING_RANGE),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and an arm answering nothing read alike.

        So the manoeuvre each fixture is meant to carry is asserted first,
        through the real parser -- without this, every case below would pass on
        a reading the decoder threw away.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["idle /= Nothing", "approaching /= Nothing",
                 "(shipUIOf idle |> Maybe.andThen .indication"
                 " |> Maybe.andThen .maneuverType) == Nothing",
                 "(shipUIOf approaching |> Maybe.andThen .indication"
                 " |> Maybe.andThen .maneuverType)"
                 " == Just EveOnline.ParseUserInterface.ManeuverApproach",
                 "(shipUIOf orbiting |> Maybe.andThen .indication"
                 " |> Maybe.andThen .maneuverType)"
                 " == Just EveOnline.ParseUserInterface.ManeuverOrbit",
                 "(rowOf idle |> Maybe.andThen .objectName) == Just %s"
                 % elm_string(RAT)],
                definitions=self.definitions),
            [True] * 6)

    def test_a_ship_not_manoeuvring_is_told_to_approach(self):
        """The first of the two steps #414 made this, and it names the row.

        These fixtures carry no Selected Item panel, so the panel is showing
        something other than the row and the arm selects it -- which is the
        state every reading is in before the first press.
        """
        answer = self.repl.strings(["describeFor idle"],
                                   definitions=self.definitions)[0]
        self.assertIn("Approach", answer)
        self.assertIn(RAT, answer)
        self.assertIn("panel", answer)

    def test_the_client_s_own_manoeuvre_is_what_stops_the_commanding(self):
        """`ManeuverApproach` and nothing else.

        A rule keyed on `ManeuverOrbit` would answer `NOT COMMANDING` for the
        orbiting reading and go on commanding for the approaching one, which is
        both halves of this backwards.
        """
        self.assertEqual(
            self.repl.strings(
                ["describeFor approaching", "describeFor orbiting",
                 "describeFor keepingRange"],
                definitions=self.definitions)[0],
            "NOT COMMANDING")
        for answer in self.repl.strings(
                ["describeFor orbiting", "describeFor keepingRange"],
                definitions=self.definitions):
            self.assertIn("Approach", answer)

    def test_a_dispatched_click_is_not_the_confirmation(self):
        """The click goes out and the client does not answer: keep commanding.

        This is the whole of "a dispatched click must not count as success". The
        arm is asked twice over a reading in which the ship reports no
        manoeuvre -- which is what a click that achieved nothing leaves behind --
        and both answers have to be the command, with effects to dispatch.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["effectsFor idle /= []",
                 "(armFor idle |> Maybe.map ((/=) Nothing)) == Just True",
                 # The reading after: still nothing reported, still commanding.
                 "(armFor idle |> Maybe.map ((/=) Nothing)) == Just True"],
                definitions=self.definitions),
            [True, True, True])

    def test_the_approach_presses_no_key_at_all(self):
        """The `Q` chord PR #243 removed does not come back through this door.

        A posted key inherits the session's modifier state, and with the Fn bit
        set `Q` is macOS Quick Note -- one recorded run fronted Notes 241 times
        from the branch this manoeuvre now shares a gesture with.
        """
        self.assertEqual(
            self.repl.evaluate(["keysIn (effectsFor idle) == []"],
                               definitions=self.definitions),
            [True])

    def test_the_selection_is_a_single_click_on_the_row(self):
        """#414 replaced the double click, and this is what it dispatches now.

        The double click *was* the command: EVE answers one on a hostile ship
        with an approach, so it acted on whatever the row's position held. The
        click here only **selects**, and the command is the panel button on the
        reading after -- so the exposure that remains is one the panel's own
        naming of the selected object then catches.

        The exact effect list is asked for rather than a non-empty one, which
        is what makes the cases in this class a measurement rather than a repl
        answering `[]` to everything.
        """
        x, y = row_center(0)
        self.assertEqual(
            self.repl.evaluate(
                ["effectsFor idle == EffectOnWindow.effectsMouseClickAtLocation"
                 " EffectOnWindow.MouseButtonLeft { x = %d, y = %d }" % (x, y)],
                definitions=self.definitions),
            [True])

    def test_the_click_is_aimed_at_the_row_and_not_the_ship(self):
        """The control: a fixture answering `[]` would satisfy the key case."""
        x, y = row_center(0)
        self.assertEqual(
            self.repl.evaluate(
                ["List.member (EffectOnWindow.MouseMoveTo { x = %d, y = %d })"
                 " (effectsFor idle)" % (x, y),
                 "(effectsFor approaching) == []"],
                definitions=self.definitions),
            [True, True])


class ARowTooSmallToClickSaysSoTest(unittest.TestCase):
    """The regression the shared helper already refuses, re-asked here.

    `doubleClickUiElement` ended in a spoken decline rather than
    `Result.withDefault []`, because a branch that prints "Approach." over an
    empty effect list is this repo's signature failure.

    **#414 changed which helper that is and nearly lost the property.** The arm
    selects the row with a single click now, and both of this bot's single-click
    helpers answer `Result.withDefault []` -- so the select-then-press would
    have printed its line over nothing for a row too small to click.
    `clickUiElementOrSayItCannotBeClicked` is the answer, in
    `doubleClickUiElement`'s own words, and this class is what noticed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ApproachRepl)
        cls.definitions = [
            ApproachRepl.reading_binding("tiny", [
                flying(), tiny_rows([("5,000 m", RAT)])]),
            ApproachRepl.reading_binding("drawn", [
                flying(), overview_rows([("5,000 m", RAT, "111", True)])]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """Both rows parse; they differ in one thing, the row's height."""
        self.assertEqual(
            self.repl.evaluate(
                ["(rowOf tiny |> Maybe.andThen .objectName) == Just %s"
                 % elm_string(RAT),
                 "(rowOf drawn |> Maybe.andThen .objectName) == Just %s"
                 % elm_string(RAT)],
                definitions=self.definitions),
            [True, True])

    def test_a_row_too_small_to_click_says_so(self):
        answer = self.repl.strings(["describeFor tiny"],
                                   definitions=self.definitions)[0]
        self.assertIn("Approach", answer)
        self.assertIn("too small to click", answer)

    def test_a_row_too_small_to_click_dispatches_nothing(self):
        """Saying so and then clicking anyway would be the other failure."""
        self.assertEqual(
            self.repl.evaluate(["effectsFor tiny == []"],
                               definitions=self.definitions),
            [True])

    def test_a_row_that_can_be_clicked_still_is(self):
        """The control: the decline is about the row, not about this fixture."""
        answer = self.repl.strings(["describeFor drawn"],
                                   definitions=self.definitions)[0]
        self.assertNotIn("too small to click", answer)
        self.assertEqual(
            self.repl.evaluate(["effectsFor drawn /= []"],
                               definitions=self.definitions),
            [True])


def tiny_rows(rows):
    """Overview rows drawn too small to click.

    `uiNodeVisibleRegionLargeEnoughForClicking` wants more than three pixels in
    both directions, and a row the overview has all but scrolled out of view is
    how that happens on a live client. Everything else is `overview_rows`' shape,
    which cannot express a height.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH
        entries.append(node("OverviewScrollEntry",
                            {"_name": "overviewEntry", "itemID": "111"}, [
                                label(distance, (10, y, 50, 2)),
                                label(name, (110, y, 150, 2)),
                                label(name, (310, y, 150, 2)),
                                node("SpaceObjectIcon", {}, [
                                    node("Sprite",
                                         {"_name": "targetedByMeIndicator"}),
                                ], region=(2, y, 12, 2)),
                            ], region=(0, y, 500, 2)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


class TheWiringIsWhatTheRuleSaysTest(unittest.TestCase):
    """The claims that are not expressions, read out of the source.

    The arm and the rule are executed above; what a repl cannot see is whether
    the decision site asks the rule at all, and whether the setting reaches a
    decision rather than sitting in the record being parsed and never read --
    which is #125's shape and #195's, and this repo's signature failure.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.flat = collapsed(self.source)

    def test_the_setting_is_read_by_a_decision(self):
        """Somewhere other than the field, the default and the parser handler.

        Elm has no dynamic field access, so this is a proof rather than a search
        that came up empty: a setting whose name occurs only in those three
        places is one an operator can set and get exactly the bot they would
        have got without it, which is what `avoid-rat` shipped as in the mission
        runner (#125) and what #195 found again.
        """
        elsewhere = without_the_write_only_blocks(self.source)
        self.assertIn(
            "approachInCombat", elsewhere,
            "approachInCombat is named only where a setting is written -- the "
            "record field, the default and the parser -- so nothing reads it")
        self.assertIn(
            "botSettings.approachInCombat == AppSettings.Yes",
            collapsed(elsewhere),
            "the rule that reads the setting is not comparing it to Yes")

    def test_the_write_only_blocks_are_really_what_was_cut(self):
        """The control for the case above, which would otherwise pass on a typo.

        A block name that stopped matching would leave the whole file behind and
        the read would be "found" in the parser handler.
        """
        elsewhere = without_the_write_only_blocks(self.source)
        self.assertLess(len(elsewhere), len(self.source))
        for written in ("keepAtRange = keepAtRange",
                        ", approachInCombat : AppSettings.YesOrNo"):
            self.assertNotIn(written, elsewhere)

    def test_the_dispatch_asks_the_rule(self):
        """The decision site cases on the rule rather than carrying its own chain.

        A second copy of the ordering is a second place the exclusion lives, and
        two places that can disagree is exactly what an executable rule is for.
        """
        self.assertIn(
            "case combatManoeuvreFromSettings"
            " context.eventContext.botSettings of ManoeuvreOrbit ->",
            self.flat)
        for arm, decision in (
                ("ManoeuvreOrbit", "ensureShipIsOrbitingDecision"),
                ("ManoeuvreKeepAtRange", "ensureShipIsKeepingRangeDecision"),
                ("ManoeuvreApproach", "ensureShipIsApproachingDecision"),
                ("ManoeuvreAlign", "ensureShipIsAlignedDecision")):
            self.assertIn(
                "%s -> %s |> Maybe.withDefault decisionToFight" % (arm, decision),
                self.flat, "%s does not take %s" % (arm, decision))

    def test_the_approach_arm_reaches_the_shared_panel_shape(self):
        """One shape rather than three copies of the ordering.

        Since #414 all three manoeuvre arms are the same select-then-press with
        a different button, a different manoeuvre to read back and different
        words -- and three copies of that ordering would be three places a
        press could end up ahead of its selection. What executes the shape is
        `test_selected_item_panel_manoeuvres`.
        """
        arm = collapsed(declaration(self.source, "ensureShipIsApproaching"))
        self.assertIn("commandManoeuvreFromSelectedItemPanel", arm)
        self.assertIn("selectedItemApproachButton", arm)
        self.assertIn("ManeuverApproach", arm)
        self.assertNotIn("doubleClickUiElement", arm)

    def test_the_approach_arm_presses_no_key(self):
        """Read as well as executed, so a chord added under a settings branch
        that the fixtures above do not reach still fails.

        `declaration` starts at the type annotation, so the doc comment above it
        -- which names `vkey_E` and `vkey_W` while arguing that this arm presses
        neither -- is not in what this reads. A reader that included it would
        satisfy nothing here and fail everything, which is the mirror of the
        trap `test_saxrat_gate_panel_button` hit once: a case that passed on a
        branch's own log text rather than on what the branch did.
        """
        body = declaration(self.source, "ensureShipIsApproaching")
        for forbidden in ("KeyDown", "KeyUp", "vkey_"):
            self.assertNotIn(
                forbidden, body,
                "the approach arm names %r, so it is pressing a key again"
                % forbidden)

    def test_no_effect_anywhere_in_saxrat_presses_q(self):
        """PR #243's own case, re-asked because this change adds an approach.

        The chord it removed was on the approach path, so an approach arriving
        under a new name is exactly where it would come back.
        """
        self.assertEqual(
            re.findall(r"EffectOnWindow\.vkey_Q\b", self.source), [])

    def test_the_two_siblings_no_longer_hold_their_keys_over_a_click(self):
        """This case said the opposite until #414, and the claim it recorded
        has now come true.

        `vkey_E` for keep-at-range and `vkey_W` for orbit were the last two
        key-wrapped clicks on this hot path, and #386 was scoped to the
        approach. The sentence written here then -- that "saxrat presses no
        movement key any more" is the claim somebody will make next, and it is
        false -- is what a later reader would have gone on believing, so the
        case is inverted rather than deleted. All three arms take the panel
        now, and no movement key is posted anywhere in this bot.
        """
        for chord in ("vkey_E", "vkey_W", "vkey_Q"):
            with self.subTest(chord=chord):
                self.assertEqual(
                    re.findall(r"EffectOnWindow\.%s\b" % chord, self.source),
                    [])
        for arm, button in (("ensureShipIsKeepingRange",
                             "selectedItemKeepAtRangeButton"),
                            ("ensureShipIsOrbiting", "selectedItemOrbitButton")):
            with self.subTest(arm=arm):
                body = collapsed(declaration(self.source, arm))
                self.assertIn("commandManoeuvreFromSelectedItemPanel", body)
                self.assertIn(button, body)

    def test_the_arm_is_reached_from_the_active_target(self):
        """The row approached is the one the guns are on, like its siblings."""
        body = indented_block(
            self.source, "ensureShipIsApproachingDecision", " " * 8)
        flat = collapsed(body)
        self.assertIn("List.filter overviewEntryIsActiveTarget", flat)
        self.assertIn(
            "ensureShipIsApproaching context seeUndockingComplete.shipUI"
            " overviewEntryToAttack", flat)

    def test_the_doc_comment_states_the_cost_and_declines_a_range(self):
        """Continuous approach, its cost, and why no distance setting exists.

        The issue leaves the choice open; the decision is recorded where the
        code is rather than in a pull request nobody reads afterwards. A range
        clause would also have to *read* a distance, so the executable half of
        this is the absence of any comparison against one.
        """
        doc = collapsed(doc_comment_of(self.source, "ensureShipIsApproaching"))
        self.assertIn("zero transversal", doc)
        self.assertIn("engagement distance", doc)
        self.assertIn("7,500 m", doc)
        self.assertIn("ManeuverApproach", doc)

        code = collapsed(declaration(self.source, "ensureShipIsApproaching"))
        for forbidden in ("objectDistanceInMeters", "Meters", "<=", ">="):
            self.assertNotIn(
                forbidden, code,
                "the approach arm reads %r, so it is stopping at a range -- "
                "which needs a distance, and PILOT.md records what an "
                "unreadable client default costs" % forbidden)

    def test_the_header_documents_the_setting(self):
        """`--help` is generated from the header, so a setting absent there is
        one an operator cannot find. #161 is the app that got this backwards."""
        header = self.source[:self.source.index("module Bot exposing")]
        self.assertIn("+ `approach-in-combat`", header)
        bullet = header[header.index("+ `approach-in-combat`"):]
        bullet = bullet[:bullet.index("\n      + ")]
        self.assertIn("mutually exclusive", bullet)
        self.assertIn("double click", bullet)
        self.assertIn("transversal", bullet)


if __name__ == "__main__":
    unittest.main()
