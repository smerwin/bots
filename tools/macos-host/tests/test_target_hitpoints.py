"""Tests for the status line saying what condition the active target is in.

Issue #112. `target <name>` named the thing the guns were pointed at and said
nothing at all about it, on a large share of every combat reading -- run 27
alone has 7,917 readings naming a target. #90 exists because of that gap: nothing
told the bot its shots were doing zero damage, and the fix had to reconstruct
the answer from the combat log's outgoing lines, because no field in any reading
said what the target's health was doing. Run 27 shot an `Infested Asteroid` for
roughly 290 consecutive readings with every shot landing for zero, and a health
bar that never moved would have said so on the second reading.

**It is a parse and not a hover**, which is the question #112 left open and a
read of the live client answered. Under every `TargetInBar` the client draws
`shieldBar`, `armorBar` and `hullBar` as named containers, so there is an answer
on every reading, no mouse involved, and no competition with the ammo swap's own
weapon hover.

**The geometry is the part that had to be worked out rather than assumed, and
the obvious reading of it is wrong.** The three bars are a *ring*, drawn as two
half-circle sprites per layer, and every node under `TargetHealthBars` -- all
three containers, all six sprites, and the background -- reports the identical
141x141 region, which is the bounding box of the whole ring. There is no width
to take a ratio of; `DronesWindowEntryDroneStructure.hitpointsPercent`'s
technique next door answers nothing here. What the client stores is the fraction
itself, as `lastState` on the named container, so this is `ShipUI`'s
`_lastValue` read rather than the drone's geometry.
`TheRingCarriesNoWidthToTakeARatioOf` is that shape asserted: the fixtures give
every one of those nodes the same region, which a width-ratio implementation
cannot read anything but a constant out of.

Two properties are what make this worth having rather than merely present, and
both have cases of their own.

**The three values stay distinct.** The zero-damage case is a shield that does
not move while armour and hull sit at 100%, which any combined figure hides, so
the clause prints three numbers and the parser answers a `Hitpoints` record
rather than one percentage.

**Absent reads as absent.** A target whose bars cannot be read prints `unknown`,
never `0%`. A fabricated zero is a hull about to explode as far as any later rule
is concerned -- this repo's absent-evidence rule, in `loadRefusalFromGameLog`'s
register. Three separate ways of failing to read are executed here (no health
bars at all, one layer missing, a layer carrying no `lastState`) and all three
have to answer `Nothing` and print no digit.

**Nothing decides anything on it.** It is an instrument, and it earns the right
to drive a rule once a run has shown it reads sanely -- PR #130's posture for
`quickMessage`, which PR #153 later relaxed deliberately once there was a corpus.
`TheFieldIsAnInstrumentAndNothingActsOnIt` is what holds that line.

The rules are executed through the real `Bot.elm` in `elm repl` via the shared
harness in `prerequisites.py`, in **both** apps, and the readings are built by
running a UI tree through the **real** `EveOnline.ParseUserInterface`, the way
`test_quick_message_logged.py` and `test_saxrat_ported_guards.py` do. A Python
restatement of "what does the parser make of these nodes" would test the
restatement.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import (ElmRepl, MISSION_RUNNER_DIR, REPO_DIR, open_repl,
                           recorded_runs)

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")
MISSION_RUNNER_PARSER = os.path.join(
    MISSION_RUNNER_DIR, "EveOnline", "ParseUserInterface.elm")
SAXRAT_PARSER = os.path.join(SAXRAT_DIR, "EveOnline", "ParseUserInterface.elm")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# The ring's own measurements, read off the live client with targets locked.
# Every node under `TargetHealthBars` reports exactly this, which is the whole
# argument for reading `lastState` rather than a width.
RING_REGION = (12, 0, 141, 141)

# The two halves the client draws each layer with. Carried in the fixtures
# because their presence is what a width-ratio implementation would be reading,
# and their being the same size as their container is why it cannot.
HALF_ROTATIONS = {"Left": 0, "Right": -2.356194490192345}

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


def health_bar(layer, last_state):
    """One layer of the ring: a named container over its two half sprites.

    `last_state` of `None` builds the container without the entry, which is a
    layer the client has drawn and this reading cannot read a value out of.
    """
    entries = {"_name": layer, "_elementId": layer}
    if last_state is not None:
        entries["lastState"] = last_state
    return node("Container", entries, [
        node("Sprite", {
            "_name": "%s_%s" % (layer, half),
            "_texturePath": "res:/UI/Texture/classes/Target/%s%s.png" % (
                layer.replace("Bar", ""), half),
            "baseRotation": rotation,
        }, region=(0, 0, RING_REGION[2], RING_REGION[3]))
        for half, rotation in sorted(HALF_ROTATIONS.items())
    ], region=(0, 0, RING_REGION[2], RING_REGION[3]))


def target_health_bars(layers):
    """The `TargetHealthBars` node, which carries no `_name` of its own."""
    return node("TargetHealthBars", {}, [
        health_bar(layer, last_state) for layer, last_state in layers
    ] + [
        node("Sprite", {
            "_name": "healthBarBackground",
            "_texturePath": "res:/UI/Texture/classes/Target/targetBackground.png",
        }, region=(0, 0, RING_REGION[2], RING_REGION[3])),
    ], region=RING_REGION)


def target(name, layers, active=True):
    """A `TargetInBar` shaped the way the live client draws one.

    `layers` is the list of `(container name, lastState)` pairs to build under
    `TargetHealthBars`; an empty list leaves the node out entirely, which is a
    target bar this reading cannot say anything about.
    """
    icon_par = node("Container", {"_name": "iconPar"},
                    ([target_health_bars(layers)] if layers else [])
                    + [node("Sprite", {"_name": "circle"}, region=(-2, -2, 145, 145))],
                    region=(12, 0, 141, 141))
    children = [
        node("Container", {"_name": "barAndImageCont", "_elementId": "barAndImageCont"},
             [icon_par], region=(0, 0, 165, 150)),
        node("EveLabelSmall", {"_name": "label", "_setText": name},
             region=(0, 155, 165, 16)),
    ]
    if active:
        children.append(node("ActiveTargetIndicator", {}, region=(0, 0, 165, 150)))
    return node("TargetInBar", {"_name": "target", "label": name},
                children, region=(1000, 69, 165, 270))


def tree_with(children):
    return node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def top_level_declarations(source):
    """Every top-level declaration, as {name: body}, without its doc comment.

    `elm-format` puts exactly two blank lines between top-level declarations, so
    the split is structural rather than a guess, and both files are validated
    against `elm-format` in the same change. The doc comment is dropped because
    these cases ask which declarations *read* something, and a doc comment
    naming a function would answer yes for every declaration that explains it.
    """
    found = {}
    for block in source.split("\n\n\n"):
        body = re.sub(r"^\{-.*?-\}\n", "", block, flags=re.DOTALL)
        match = re.match(r"^([a-zA-Z][a-zA-Z0-9_]*) :", body)
        if match is not None:
            found[match.group(1)] = body
    return found


def declaration(source, name):
    """One top-level declaration, or a failure naming what was looked for."""
    declarations = top_level_declarations(source)
    if name not in declarations:
        raise AssertionError("no top-level declaration named " + name)
    return declarations[name]


def parser_block(source):
    """The whole of the target-hitpoints parse, for the byte-for-byte compare."""
    start = source.index("{-| What the target bar's three rings say about")
    end = source.index("\n\n\n", source.index("parseTargetHitpointsPercent targetNode ="))
    return source[start:end]


class SaxratRepl(ElmRepl):
    """The same harness, pointed at saxrat rather than the mission runner."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-target-hitpoints-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class MissionRunnerRepl(ElmRepl):
    """The shared harness with the parser modules the fixtures need."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "mission-target-hitpoints-repl-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


def reading_binding(name, children):
    """A `let`-free binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what the cases assert on is what the bot
    would have been handed rather than a record written out by hand.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, '"""%s"""' % json.dumps(tree_with(children)))


def hitpoints(shield, armor, structure):
    """A `Hitpoints` literal, for the rules that take one directly."""
    return "(Just { shield = %d, armor = %d, structure = %d })" % (
        shield, armor, structure)


HURT = [("shieldBar", 0.58), ("armorBar", 1), ("hullBar", 1)]
UNTOUCHED = [("shieldBar", 1), ("armorBar", 1), ("hullBar", 1)]
# Run 27's shape: the shield does not move and neither does anything else. The
# numbers are the client's own, watched live on one `Centii Plague` as its
# shield collapsed and began to regenerate.
COLLAPSED = [("shieldBar", 4.390289566297253e-06),
             ("armorBar", 0.24838381950695254),
             ("hullBar", 1)]
# The two values CLAUDE.md records `ShipUI.hitpointsPercent` producing for
# single readings, as `lastState` fractions. Nothing in the corpus says the
# target's ring cannot do the same thing, and a run is what would say.
GARBAGE = [("shieldBar", -10218.21), ("armorBar", 21328.22), ("hullBar", 1)]
NO_HULL_BAR = [("shieldBar", 1), ("armorBar", 1)]
HULL_WITHOUT_A_VALUE = [("shieldBar", 1), ("armorBar", 1), ("hullBar", None)]

DEFINITIONS = [
    reading_binding("hurt", [target("Render Alvi", HURT)]),
    reading_binding("untouched", [target("Infested Asteroid", UNTOUCHED)]),
    reading_binding("collapsed", [target("Centii Plague", COLLAPSED)]),
    reading_binding("garbage", [target("Render Alvi", GARBAGE)]),
    reading_binding("noBars", [target("Render Alvi", [])]),
    reading_binding("noHullBar", [target("Render Alvi", NO_HULL_BAR)]),
    reading_binding("hullWithoutAValue",
                    [target("Render Alvi", HULL_WITHOUT_A_VALUE)]),
    reading_binding("inactive", [target("Render Alvi", HURT, active=False)]),
    reading_binding("noTargets", []),
]


def active_hitpoints(reading):
    return "(%s |> Maybe.map activeTargetHitpointsPercent)" % reading


def clause(reading):
    """What the status line would print for `reading`, as a plain `String`.

    The sentinel is deliberately a sentence no branch of the rule can produce,
    so a fixture that stopped parsing shows up as itself rather than as an
    unreadable bar -- which is the one confusion these cases must not have.
    """
    return ("(%s |> Maybe.map (activeTargetHitpointsPercent"
            " >> describeTargetHitpoints)"
            ' |> Maybe.withDefault "this reading did not parse at all")' % reading)


class TargetHitpointsCases:
    """The cases both apps run. Subclassed once per app, below.

    The parse and the two rules are the same declarations under the same names
    in both apps -- the field, the lookup and the rendering are facts about the
    client, not about which bot is flying -- while the status line each clause is
    placed in is not, which the wiring cases below check separately per app.
    """

    REPL_CLASS = None
    BOT_ELM = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(cls.REPL_CLASS)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_parse_into_the_readings_the_cases_assume(self):
        """The trees first, before anything is concluded from them.

        A case built on a tree the parser makes nothing of would pass or fail
        for reasons that have nothing to do with the rule under test.
        """
        answers = self.repl.evaluate(
            ["(hurt |> Maybe.map (.targets >> List.length)) == Just 1",
             "(hurt |> Maybe.map (.targets >> List.any .isActiveTarget)) == Just True",
             "(inactive |> Maybe.map (.targets >> List.any .isActiveTarget)) == Just False",
             "(noTargets |> Maybe.map (.targets >> List.length)) == Just 0",
             "(hurt |> Maybe.map (.targets >> List.any"
             " (.barAndImageCont >> (/=) Nothing))) == Just True"],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 5,
            "the parser does not make of these trees what the cases below "
            "assume it does, so nothing they conclude would mean anything")

    def test_the_three_layers_are_read_and_stay_distinct(self):
        """Three numbers out of three bars, each one its own.

        The zero-damage case #90 was filed on is a shield that does not move
        while armour and hull sit at 100%, so a rule that collapsed the three
        into one figure -- or that read one bar three times -- would hide the
        exact reading this whole change exists to produce.
        """
        answers = self.repl.evaluate(
            [active_hitpoints("hurt") + " == Just " + hitpoints(58, 100, 100),
             active_hitpoints("untouched") + " == Just " + hitpoints(100, 100, 100),
             active_hitpoints("collapsed") + " == Just " + hitpoints(0, 25, 100)],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 3,
            "the three layers are not being read separately off shieldBar, "
            "armorBar and hullBar")

    def test_a_bar_that_cannot_be_read_is_unknown_and_never_zero(self):
        """The house rule, executed three ways it can fail.

        A `0%` invented from a widget that was not there is a hull about to
        explode as far as any later rule is concerned, and this repo has paid
        for absent-evidence-as-a-finding several times over. All three shapes
        have to answer `Nothing`, and none of them may print a digit.
        """
        answers = self.repl.evaluate(
            [active_hitpoints("noBars") + " == Just Nothing",
             active_hitpoints("noHullBar") + " == Just Nothing",
             active_hitpoints("hullWithoutAValue") + " == Just Nothing",
             active_hitpoints("inactive") + " == Just Nothing",
             active_hitpoints("noTargets") + " == Just Nothing"],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 5,
            "a target whose bars cannot be read is answering something other "
            "than Nothing")

        rendered = self.repl.strings(
            [clause("noBars"), clause("noHullBar"),
             clause("hullWithoutAValue"), clause("noTargets"),
             "(describeTargetHitpoints Nothing)"],
            definitions=DEFINITIONS)
        for text in rendered:
            self.assertIn("unknown", text, text)
            self.assertNotIn("0%", text, text)
            self.assertFalse(
                any(character.isdigit() for character in text),
                "an unreadable bar printed a number: " + text)

    def test_a_bar_really_at_zero_prints_zero_and_not_unknown(self):
        """The other side of the same distinction, and it is a real reading.

        `shieldBar` was watched live at 4.39e-06 with the shield genuinely gone,
        so 0% is a value this field must be able to say. If it read `unknown`
        there, the clause could not tell a dead shield from an absent widget --
        which is the same collapse in the opposite direction.
        """
        [rendered] = self.repl.strings([clause("collapsed")],
                                       definitions=DEFINITIONS)
        self.assertIn("Shield: 0%", rendered)
        self.assertNotIn("unknown", rendered)

    def test_the_clause_reads_like_the_ships_own_line(self):
        """`Shield: 58%  Armor: 100%` is what the ship's line already says.

        #112 asks for the two to read alike so an operator scanning a column of
        readings does not have to learn a second spelling, and all three layers
        have to be nameable rather than positional.
        """
        [rendered] = self.repl.strings([clause("hurt")], definitions=DEFINITIONS)
        self.assertIn("Shield: 58%", rendered)
        self.assertIn("Armor: 100%", rendered)
        self.assertIn("Hull: 100%", rendered)

    def test_the_ring_carries_no_width_to_take_a_ratio_of(self):
        """The geometry, asserted rather than described in a comment.

        Every node the fixtures build under `TargetHealthBars` -- the three
        containers, their six half-circle sprites and the background -- carries
        the identical region, which is what the live client reports. So a
        width-ratio implementation of this, the technique
        `DronesWindowEntryDroneStructure.hitpointsPercent` uses next door, can
        only ever answer one constant here. The parse has to be reading the
        client's own `lastState`, and these are three readings a constant cannot
        satisfy at once.
        """
        regions = set()

        def walk(entry):
            name = (entry["dictEntriesOfInterest"] or {}).get("_name") or ""
            if name.startswith(("shieldBar", "armorBar", "hullBar",
                                "healthBarBackground")):
                regions.add((entry["dictEntriesOfInterest"]["_displayWidth"],
                             entry["dictEntriesOfInterest"]["_displayHeight"]))
            for child in entry["children"]:
                walk(child)

        walk(target("Render Alvi", HURT))
        self.assertEqual(
            len(regions), 1,
            "the fixture no longer gives every ring node one region, so it no "
            "longer stands in for what the live client draws")

        answers = self.repl.evaluate(
            [active_hitpoints("hurt") + " == Just " + hitpoints(58, 100, 100),
             active_hitpoints("untouched") + " == Just " + hitpoints(100, 100, 100),
             active_hitpoints("collapsed") + " == Just " + hitpoints(0, 25, 100)],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 3,
            "three trees whose nodes are all one size answered three different "
            "things only if the value came from somewhere other than a width")

    def test_a_layer_at_full_decodes_from_the_integer_the_client_writes(self):
        """`lastState` is `1`, not `1.0`, on a bar that has taken nothing.

        Read live: every layer of a freshly locked target carries the JSON
        integer. A decoder that accepted only a float would answer `Nothing` for
        an untouched target, which is the reading a run spends most of its time
        on.
        """
        [answer] = self.repl.evaluate(
            [active_hitpoints("untouched") + " == Just " + hitpoints(100, 100, 100)],
            definitions=DEFINITIONS)
        self.assertTrue(answer)

    def test_the_percentages_are_the_raw_reading_rather_than_a_clamped_one(self):
        """A garbage value is printed, not tidied into a plausible one.

        `ShipUI.hitpointsPercent` is the same kind of read and CLAUDE.md records
        it producing -1021821% and 2132822% for single readings. A value silently
        clamped into [0, 100] reads exactly like a real one, and this field's
        whole job on its first run is to show whether it reads sanely -- which a
        clamp would make impossible to tell.
        """
        answers = self.repl.strings(
            [clause("garbage"),
             "(describeTargetHitpoints " + hitpoints(-1021821, 100, 100) + ")"],
            definitions=DEFINITIONS)
        # Asked of the parse as well as of the rendering, because a clamp put in
        # either place produces the same reassuring number.
        self.assertIn("Shield: -1021821%", answers[0])
        self.assertIn("Armor: 2132822%", answers[0])
        self.assertIn("Shield: -1021821%", answers[1])

    def test_the_two_rules_are_pure_functions_of_what_they_are_handed(self):
        """Neither reaches for a decision context, so a case can execute them.

        This is the shape #106 records the cost of getting wrong: a rule
        reachable only through a whole `BotDecisionContext` "could not be
        executed ... which is exactly why the shipped version was checked by
        reading it".
        """
        source = source_of(self.BOT_ELM)
        self.assertIn(
            "activeTargetHitpointsPercent : ReadingFromGameClient -> "
            "Maybe EveOnline.ParseUserInterface.Hitpoints",
            collapsed(source))
        self.assertIn(
            "describeTargetHitpoints : Maybe EveOnline.ParseUserInterface"
            ".Hitpoints -> String",
            collapsed(source))
        for name in ("activeTargetHitpointsPercent", "describeTargetHitpoints"):
            body = declaration(source, name)
            self.assertNotIn("BotDecisionContext", body, name)
            self.assertNotIn("context", body, name)


class TheFieldIsAnInstrumentAndNothingActsOnIt(unittest.TestCase):
    """#112's scope, asserted rather than described in a comment.

    Nothing decides anything on this field in this change: it earns the right to
    drive a rule once a run has shown it reads sanely. That is PR #130's posture
    for `quickMessage`, and PR #153's later relaxation is what it looks like when
    the argument has been made -- one named reader admitted, deliberately, once
    there was a corpus. Until then a second reader has to fail this case.
    """

    def sources(self):
        return {"mission runner": source_of(MISSION_RUNNER_BOT_ELM),
                "saxrat": source_of(SAXRAT_BOT_ELM)}

    @staticmethod
    def code_only(source):
        """The source with its prose removed.

        Writing about this field is expected and encouraged; a *read* of it is
        what must not spread. `{- -}` blocks are these files' doc comments, and
        a whole line beginning `--` is prose too. Only whole comment lines are
        dropped, never a trailing `--`, so no string literal is touched.
        """
        code = re.sub(r"\{-.*?-\}", "", source, flags=re.DOTALL)
        return "\n".join(
            "" if line.lstrip().startswith("--") else line
            for line in code.split("\n"))

    def test_the_targets_hitpoints_are_reached_one_way_only(self):
        """One lookup, whatever spelling a second one might have used.

        Asked of every line rather than of one phrase: `Maybe.andThen
        .hitpointsPercent` is this rule's spelling and `target.hitpointsPercent`
        is not, so counting the phrase would let the second one through. The
        ship's own gauge shares the field name and is the reason the exemption
        exists at all.
        """
        for app, source in self.sources().items():
            declarations = top_level_declarations(source)
            own = self.code_only(declarations["activeTargetHitpointsPercent"])
            for name, block in declarations.items():
                if name == "activeTargetHitpointsPercent":
                    continue
                body = self.code_only(block)
                if "hitpointsPercent" not in body.replace(
                        "plausibleHitpointsPercent", ""):
                    continue
                # The ship's own gauge shares the field name, and every other
                # reader of it in either app is that one. The exemption is per
                # declaration rather than per line because the ship UI is often
                # named a line or two above the field.
                self.assertTrue(
                    "shipUI" in body or "ShipUI" in body,
                    "%s: %s reads a hitpoints field and is not about the "
                    "ship's own gauge" % (app, name))
            self.assertIn(
                "Maybe.andThen .hitpointsPercent", own,
                app + ": activeTargetHitpointsPercent no longer reads the "
                "field these cases think it does")

    def test_only_the_status_line_reads_the_two_rules(self):
        # The declarations are cut out of the *source* and stripped afterwards:
        # removing the doc comments first leaves a leading blank line where each
        # one was, which `top_level_declarations` no longer recognises -- a
        # reader that finds nothing and asserts on it is a case passing having
        # checked nothing, which is what this file exists to prevent.
        for app, source in self.sources().items():
            code = self.code_only(source)
            status = self.code_only(declaration(source, "statusTextFromState"))
            for name in ("activeTargetHitpointsPercent", "describeTargetHitpoints"):
                own = self.code_only(declaration(source, name))
                self.assertEqual(
                    code.count(name),
                    # its own signature and its own definition line
                    own.count(name)
                    + status.count(name),
                    "%s: %s is read outside statusTextFromState and its own "
                    "declaration" % (app, name))
                self.assertEqual(
                    status.count(name), 1,
                    "%s: the status line reads %s more than once" % (app, name))

    def test_no_decision_branch_names_the_field(self):
        # The named branches a target's condition would obviously be wired into
        # first. None of them may consult it in this change.
        branches = ("shouldAttackOverviewEntry",
                    "activateOneOfTheLockedTargets",
                    "targetsToUnlockFromReadingFromGameClient")
        for app, source in self.sources().items():
            declarations = top_level_declarations(source)
            found = [branch for branch in branches if branch in declarations]
            self.assertTrue(
                found, app + ": none of the named branches exist any more, so "
                "this case is checking nothing")
            for branch in found:
                body = self.code_only(declarations[branch])
                self.assertNotIn("hitpointsPercent", body,
                                 "%s: %s decides on the target's condition"
                                 % (app, branch))
                self.assertNotIn("activeTargetHitpointsPercent", body,
                                 "%s: %s decides on the target's condition"
                                 % (app, branch))


class TheParseIsTheSameInBothApps(unittest.TestCase):
    """The two vendored copies carry one parse, byte for byte.

    `test_game_log_channel.py`'s check, for its reason: a change that lands in
    one copy and silently not the other is its own bug, and here it would be a
    quiet one -- the app that lacks it prints `unknown` on every reading, which
    is indistinguishable from a client that does not draw the bars.

    The other four vendored copies are deliberately not included. Their
    `parseTarget` already diverges from these two (they recognise only
    `ActiveTargetOnBracket`, where this fork added `ActiveTargetIndicator`), so
    the maintained pair is the unit this repo already keeps in step.
    """

    def test_the_field_is_on_both_target_aliases(self):
        for path in (MISSION_RUNNER_PARSER, SAXRAT_PARSER):
            source = source_of(path)
            alias = source[source.index("type alias Target ="):]
            alias = alias[:alias.index("\n    }")]
            self.assertIn("hitpointsPercent : Maybe Hitpoints", alias, path)
            self.assertIn(
                "hitpointsPercent = parseTargetHitpointsPercent targetNode",
                source, path)

    def test_both_copies_carry_the_same_parse(self):
        reference = parser_block(source_of(MISSION_RUNNER_PARSER))
        self.assertEqual(parser_block(source_of(SAXRAT_PARSER)), reference)

    def test_the_parse_reads_the_three_containers_by_name(self):
        block = parser_block(source_of(MISSION_RUNNER_PARSER))
        for container in ("shieldBar", "armorBar", "hullBar"):
            self.assertIn('"%s"' % container, block, container)
        self.assertIn('"lastState"', block)

    def test_the_parse_takes_no_width(self):
        # The property the geometry argument rests on, made structural. A ratio
        # against a display region cannot creep back in without failing here.
        block = parser_block(source_of(MISSION_RUNNER_PARSER))
        for reached_for in ("totalDisplayRegion", ".width", "droneGaugeBar"):
            self.assertNotIn(reached_for, block, reached_for)

    def test_both_apps_carry_the_same_two_rules(self):
        mission = source_of(MISSION_RUNNER_BOT_ELM)
        saxrat = source_of(SAXRAT_BOT_ELM)
        for name in ("activeTargetHitpointsPercent", "describeTargetHitpoints"):
            self.assertEqual(declaration(mission, name),
                             declaration(saxrat, name), name)


class TheStatusLineCarriesIt(unittest.TestCase):
    """The wiring, which differs per app because the two status lines do.

    The mission runner's clause is `target <name>` on the middle line; saxrat's
    is `Current target: <name>.`. Both name the target and then its condition,
    and both print the condition only where there is a target to have one -- run
    27 has 10,372 readings naming none, and a `Shield/Armor/Hull unknown` on
    every one of them would be noise rather than a reading.
    """

    def test_the_mission_runner_names_the_condition_after_the_target(self):
        clause_source = self.target_clause(source_of(MISSION_RUNNER_BOT_ELM))
        self.assertIn(
            'describeTargetHitpoints (activeTargetHitpointsPercent '
            'readingFromGameClient)', collapsed(clause_source))
        self.assertIn('"target "', collapsed(clause_source))

    def test_saxrat_names_the_condition_after_the_target(self):
        clause_source = self.target_clause(source_of(SAXRAT_BOT_ELM))
        self.assertIn(
            'describeTargetHitpoints (activeTargetHitpointsPercent '
            'readingFromGameClient)', collapsed(clause_source))
        self.assertIn('"Current target: "', collapsed(clause_source))

    @staticmethod
    def target_clause(source):
        """The `describeCurrentTarget` binding, which is a `let` binding.

        Read to the next line indented no further than its own name, for
        `test_saxrat_opportunity_shadow.py`'s reason: reading to the next `in`
        lets a second binding beside it satisfy the assertion.
        """
        start = source.index("                        describeCurrentTarget =")
        lines = source[start:].split("\n")
        body = [lines[0]]
        for line in lines[1:]:
            if line.strip() and not line.startswith(" " * 25):
                break
            body.append(line)
        return "\n".join(body)

    def test_a_reading_with_no_target_says_only_that(self):
        for app, path in (("mission runner", MISSION_RUNNER_BOT_ELM),
                          ("saxrat", SAXRAT_BOT_ELM)):
            clause_source = self.target_clause(source_of(path))
            nothing_branch = clause_source[clause_source.index("Nothing ->"):]
            nothing_branch = nothing_branch[:nothing_branch.index("Just ")]
            self.assertNotIn("describeTargetHitpoints", nothing_branch, app)


class TheCorpusSaysWhyThisIsWorthReading(unittest.TestCase):
    """Run 27, recounted as relations rather than as the issue's numbers.

    A corpus that grows must not turn a true claim red, so what is asserted is
    the shape: the status line named a target on a large share of readings, and
    said nothing whatever about its condition on any of them. The second half is
    what this change ends, and it is also the check that the clause being looked
    for is genuinely new rather than something already printed under another
    spelling.
    """

    def test_the_target_was_named_often_and_never_described(self):
        naming = describing = 0
        for _, path in recorded_runs("27", "29", "30", "34"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if re.search(r"\btarget [A-Z]", line):
                        naming += 1
                        if "Hull:" in line:
                            describing += 1
        self.assertGreater(
            naming, 100,
            "no recorded run names a target in its status line, so the clause "
            "this change adds to is not where these cases think it is")
        self.assertEqual(
            describing, 0,
            "a recorded run already printed a target's hull, so this field was "
            "not absent and the argument for adding it does not hold")

    def test_run_27_shot_something_it_never_hurt(self):
        # #90's incident, which is the argument in the doc comment. Asserted as
        # the relation -- the object was the target for a long stretch -- rather
        # than as the issue's "roughly 290", which a re-derivation could move.
        for name, path in recorded_runs("27"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            self.assertGreater(
                text.count("target Infested Asteroid"), 50,
                "run %s no longer holds the stretch this argument rests on" % name)


class MissionRunnerTargetHitpointsTest(TargetHitpointsCases, unittest.TestCase):
    REPL_CLASS = MissionRunnerRepl
    BOT_ELM = MISSION_RUNNER_BOT_ELM


class SaxratTargetHitpointsTest(TargetHitpointsCases, unittest.TestCase):
    REPL_CLASS = SaxratRepl
    BOT_ELM = SAXRAT_BOT_ELM


if __name__ == "__main__":
    unittest.main()
