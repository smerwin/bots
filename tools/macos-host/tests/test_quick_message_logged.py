"""Tests for both apps printing EVE's transient quick message instead of dropping it.

Issue #123. `ParsedUserInterface.layerAbovemain.quickMessage` carries the literal
text of the client's transient centre-screen popup and has been parsed on every
reading since the mission runner was added. It is read **nowhere**: five
references in each app's `EveOnline/ParseUserInterface.elm`, zero in either
`Bot.elm`, and no test anywhere. So every message this client has ever shown a
bot was decoded into a string and thrown away, and **no wording has ever been
recorded**.

**These cases are about logging it, not about acting on it**, and one of them
asserts that directly. A matcher written now would rest on guessed strings, which
is the trap #92 documents -- a rule keyed on a word list the client's vocabulary
outgrew twice with nobody noticing. What the change buys is that the next run
puts the vocabulary into the corpus; the matcher comes after there is one.

**The corpus arrived and #146 wrote the first matcher against it**, on one
message -- the drone-launch refusal, in `test_drone_launch_refusal.py`. What that
changes here is narrow and the two cases at the bottom of this file now hold the
line where it moved. That rule reads `quickMessageOnScreen`, this reading's
sighting, and never `memory.quickMessage`, the aged one; and it is the *only*
matcher on the message, which is what keeps "one message wired deliberately"
from becoming "a quick message means something went wrong".

Two design questions the cases pin, because both can be got wrong quietly:

- **Persistence.** A popup is transient and a reading is seconds apart, so the
  clause carries the last sighting forward with an age rather than reporting only
  the live value. The danger of that is a stale message read as current, so
  `describeQuickMessage` names which it is in every branch and these cases assert
  both wordings and that they differ.
- **Whether the head-only parse drops messages.** It does, in two places:
  `parseQuickMessage` filters the layer's descendants for `QuickMessage` and
  takes `List.head`, then takes the head of that node's display texts. Both are
  executed here against real UI trees carrying two of each, and the clause is
  asserted to say what it dropped -- which is what turns #123's last Unverified
  item into something a run can answer.

The rules are executed through the real `Bot.elm` in `elm repl` via the shared
harness in `prerequisites.py`, in **both** apps, rather than restated in Python:
a Python restatement of "what does the clause say" tests the restatement. The
readings are built by running a UI tree through the **real**
`EveOnline.ParseUserInterface`, the way `test_saxrat_ported_guards.py` does, so a
hand-written record cannot drift from what the parser would have produced.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import (ElmRepl, MISSION_RUNNER_DIR, REPO_DIR,
                           elm_json_literal, open_repl)

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# The character budget the status line caps a message at. Read out of `Bot.elm`
# below rather than trusted from here; this copy only shapes the fixtures.
EXPECTED_BUDGET = 400

# A message with everything a normalising renderer would quietly destroy: mixed
# case, a colon, an apostrophe, an exclamation mark, a comma and a run of two
# spaces. No client wording is known -- that is the whole of #123 -- so this is
# deliberately not a guess at one.
AWKWARD_TEXT = "You're at MAXIMUM targets: 6 of 6, no more!  Try again."

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


def label(text, region):
    return node("EveLabelMedium", {"_name": "label", "_setText": text},
                region=region)


def quick_message(lines, top):
    """A `QuickMessage` node with one label per line.

    The node itself carries no text, so `getAllContainedDisplayTexts` yields the
    labels in order and the parser's `List.head` takes the first -- which is the
    second place a message can lose part of itself, and what
    `displayTextsInMessage` counts.
    """
    return node("QuickMessage", {}, [
        label(text, (500, top + 20 * index, 400, 16))
        for index, text in enumerate(lines)
    ], region=(500, top, 400, 20 * max(1, len(lines))))


def layer_abovemain(messages):
    """The `l_abovemain` layer, holding one `QuickMessage` per entry.

    Identified by `_name`, which is what `parseLayerAbovemainFromUITreeRoot`
    matches on, and given a display region because that parser navigates by one.
    """
    return node("LayerCore", {"_name": "l_abovemain"}, [
        quick_message(lines, 400 + 100 * index)
        for index, lines in enumerate(messages)
    ], region=(0, 0, 1920, 1080))


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
    the split is structural rather than a guess -- and the file is validated
    against `elm-format` in the same change, so it cannot drift.

    The doc comment is dropped rather than kept, because these cases ask which
    declarations *read* something: a doc comment naming a field would answer yes
    for every declaration that merely explains it.
    """
    found = {}
    for block in source.split("\n\n\n"):
        body = re.sub(r"^\{-.*?-\}\n", "", block, flags=re.DOTALL)
        match = re.match(r"^([a-zA-Z][a-zA-Z0-9_]*) :", body)
        if match is not None:
            found[match.group(1)] = body
    return found


def declaration(source, name):
    """One top-level declaration, or a failure naming what was looked for.

    A missing name must not read as "nothing matched": that is the shape that
    makes a structural case pass having checked nothing.
    """
    declarations = top_level_declarations(source)
    if name not in declarations:
        raise AssertionError("no top-level declaration named " + name)
    return declarations[name]


def integer_constant(source, name):
    match = re.search(
        r'^' + name + r' : Int\n' + name + r' =\n\s+(-?\d+)',
        source, re.MULTILINE)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return int(match.group(1))


class SaxratRepl(ElmRepl):
    """The same harness, pointed at saxrat rather than the mission runner."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-quickmessage-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class MissionRunnerRepl(ElmRepl):
    """The shared harness with the parser modules the fixtures need."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "mission-quickmessage-repl-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


def reading_binding(name, children):
    """A `let`-free binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what the cases assert on is what the bot
    would have been handed. `Maybe.withDefault` is not available for a
    `ParsedUserInterface`, so the binding stays a `Maybe` and every expression
    maps over it.

    The literal comes from `elm_json_literal` rather than being written out
    here, because getting that wrong is not a broken fixture -- it is a case
    that passes having asserted against a reading that never arrived. See its
    doc comment.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, elm_json_literal(tree_with(children)))


def sighting(text, readings_since=0, messages=1, display_texts=1):
    """A `QuickMessageSighting` literal, for the rules that take one directly."""
    return ("{ text = %s, messagesInLayer = %d, displayTextsInMessage = %d,"
            " readingsSince = %d }"
            % (json.dumps(text), messages, display_texts, readings_since))


class QuickMessageCases:
    """The cases both apps run. Subclassed once per app, below.

    Both apps carry the same rules under the same names -- the parser field is
    identical and so is what has to be recorded -- while the status line each
    clause is placed in is not, which is what the wiring cases below check
    separately per app.

    The clause's *wording* is one of the things that is not shared, since #242
    shortened saxrat's status line and left the mission runner's alone. What
    both have to say is the same and is what every case here asserts: whether
    the message is on the screen now, said first and never implied, and an age
    where it is not. Each subclass names the two markers its own app prints, so
    a drift in either is a failure rather than a loosened assertion.
    """

    REPL_CLASS = None
    BOT_ELM = None

    # What the clause says for a message on this reading, and for one carried
    # forward. Each has to be absent from the other's clause, which is what the
    # case below asserts in both directions -- the mission runner's pair is
    # `(on screen now)` against `NOT on screen now`, where a marker chosen
    # carelessly would be a substring of the other and assert nothing.
    LIVE_MARKER = None
    STALE_MARKER = None

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
            ["(one |> Maybe.map (.layerAbovemain >> (/=) Nothing)) == Just True",
             "(one |> Maybe.andThen .layerAbovemain"
             " |> Maybe.map (.quickMessage >> (/=) Nothing)) == Just True",
             "(one |> Maybe.andThen .layerAbovemain |> Maybe.andThen .quickMessage"
             " |> Maybe.map .text) == Just " + json.dumps(AWKWARD_TEXT),
             "(two |> Maybe.andThen .layerAbovemain |> Maybe.andThen .quickMessage"
             " |> Maybe.map .text) == Just \"first message\"",
             "(empty |> Maybe.map (.layerAbovemain >> (==) Nothing)) == Just True"],
            definitions=[
                reading_binding("one", [layer_abovemain([[AWKWARD_TEXT]])]),
                reading_binding("two", [layer_abovemain(
                    [["first message"], ["second message"]])]),
                reading_binding("empty", []),
            ])
        self.assertEqual(
            answers, [True] * 5,
            "the parser does not make of these trees what the cases below "
            "assume it does, so nothing they conclude would mean anything")

    def test_the_text_is_reproduced_rather_than_tidied_up(self):
        """Case, punctuation and interior spacing survive to the status line.

        The point of printing this is that the wording becomes the evidence a
        matcher is later written against, and every one of these is something a
        matcher could turn on. A renderer that lower-cases or strips punctuation
        would leave the corpus useless in a way nothing downstream could undo.
        """
        [rendered] = self.repl.strings(
            ["quickMessageTextForStatusLine " + json.dumps(AWKWARD_TEXT)])
        self.assertEqual(rendered, AWKWARD_TEXT)

    def test_a_message_short_enough_to_print_whole_is_printed_whole(self):
        budget = integer_constant(source_of(self.BOT_ELM),
                                  "quickMessageStatusCharacterBudget")
        exactly = "x" * budget
        [rendered] = self.repl.strings(
            ["quickMessageTextForStatusLine " + json.dumps(exactly)])
        self.assertEqual(
            rendered, exactly,
            "a message exactly at the budget is not over it")

    def test_the_cap_is_generous_and_says_so_when_it_bites(self):
        """Capping is allowed; capping silently is not.

        #123 asks for the text to be usable as evidence later, so a clause that
        quietly ends mid-sentence would read as the client's whole wording. The
        clause names both numbers where it cuts and says nothing where it does
        not.
        """
        source = source_of(self.BOT_ELM)
        budget = integer_constant(source, "quickMessageStatusCharacterBudget")
        self.assertGreaterEqual(
            budget, 200,
            "a few characters of a popup is not evidence anything can be "
            "written against")

        long_text = "A" * (budget + 37)
        answers = self.repl.strings(
            ["quickMessageTextForStatusLine " + json.dumps(long_text),
             "describeQuickMessage (Just " + sighting(long_text) + ")",
             "describeQuickMessage (Just " + sighting("A" * budget) + ")"])
        self.assertEqual(answers[0], "A" * budget)
        self.assertIn("CAPPED", answers[1])
        self.assertIn(str(budget), answers[1])
        self.assertIn(str(budget + 37), answers[1],
                      "the clause has to say how much there was, or a reader "
                      "cannot tell how much is missing")
        self.assertNotIn("CAPPED", answers[2])

    def test_a_newline_is_escaped_rather_than_emitted(self):
        """The status line is line-structured and the message is not.

        The host prints the status text after the tick marker and
        `stall_watch.py` reads the first line, so a raw newline inside a message
        would split a clause across two log lines. Escaping is reversible where
        dropping the rest of the message is not.
        """
        # Compared inside Elm rather than in Python, because `elm repl` escapes
        # a control character on its way out: a message that really carried a
        # newline and one that carried the two characters `\` and `n` print
        # identically, so a Python-side comparison passes either way. Confirmed
        # by mutation -- removing the newline escape survived that version of
        # this case.
        answers = self.repl.evaluate([
            "quickMessageTextForStatusLine "
            + json.dumps("first line\nsecond line")
            + " == " + json.dumps("first line\\nsecond line"),
            "not (String.contains \"\\n\" (quickMessageTextForStatusLine "
            + json.dumps("first line\nsecond line") + "))",
            "quickMessageTextForStatusLine " + json.dumps("a\tb")
            + " == " + json.dumps("a\\tb"),
            "quickMessageTextForStatusLine " + json.dumps("a\rb")
            + " == " + json.dumps("a\\rb"),
            "quickMessageTextForStatusLine " + json.dumps("back\\slash")
            + " == " + json.dumps("back\\\\slash"),
        ])
        self.assertEqual(answers, [True] * 5)

    def test_the_clause_says_plainly_when_there_is_nothing_to_report(self):
        """Printed on the quiet readings too.

        A clause that appears only when there is something to say leaves "the
        client said nothing" and "nothing is reading the client" grepping
        identically, and telling those apart is the first thing a run has to
        answer.
        """
        [nothing] = self.repl.strings(["describeQuickMessage Nothing"])
        self.assertIn("Quick message", nothing)
        self.assertIn("none", nothing.lower())
        self.assertNotEqual(nothing.strip(), "")

    def test_live_and_carried_forward_do_not_read_the_same(self):
        """The whole safety of carrying a message forward.

        A stale message printed as if it were current would be worse than not
        printing one at all: a later reader would date the wording to the wrong
        decision. So the clause states which it is, first, and names the age.
        """
        answers = self.repl.strings(
            ["describeQuickMessage (Just " + sighting(AWKWARD_TEXT, 0) + ")",
             "describeQuickMessage (Just "
             + sighting(AWKWARD_TEXT, 7) + ")"])
        live, stale = answers

        self.assertIn(AWKWARD_TEXT, live)
        self.assertIn(AWKWARD_TEXT, stale)
        self.assertNotEqual(live, stale)

        self.assertIn(self.LIVE_MARKER, live)
        self.assertNotIn(self.STALE_MARKER, live)

        self.assertIn(self.STALE_MARKER, stale)
        self.assertNotIn(self.LIVE_MARKER, stale)
        self.assertIn("7", stale,
                      "a carried-forward message has to name its age, or a "
                      "reader cannot date the wording to a decision")

    def test_the_age_advances_while_no_message_is_on_the_screen(self):
        """Folded over a run of readings, which is where this can be wrong.

        A rule that failed to advance would report every carried message as
        current; one that failed to reset would report a live message as stale.
        Both directions are asked.
        """
        seen = "Just " + sighting("popup")
        fold = ("List.foldl"
                " (\\onScreenNow before ->"
                " quickMessageAfterReading"
                " { onScreenNow = onScreenNow, before = before })"
                " Nothing")
        answers = self.repl.evaluate([
            # Nothing has ever been seen, so there is nothing to carry.
            "(%s [ Nothing, Nothing, Nothing ]) == Nothing" % fold,
            # Seen once, then four quiet readings.
            "(%s [ %s, Nothing, Nothing, Nothing, Nothing ]"
            " |> Maybe.map .readingsSince) == Just 4" % (fold, seen),
            "(%s [ %s, Nothing, Nothing, Nothing, Nothing ]"
            " |> Maybe.map .text) == Just \"popup\"" % (fold, seen),
            # A message on the screen is age zero, whatever came before.
            "(%s [ %s, Nothing, Nothing, Just %s ]"
            " |> Maybe.map .readingsSince) == Just 0"
            % (fold, seen, sighting("newer popup")),
            "(%s [ %s, Nothing, Nothing, Just %s ]"
            " |> Maybe.map .text) == Just \"newer popup\""
            % (fold, seen, sighting("newer popup")),
            # And the reading it is seen on is age zero, not one.
            "(%s [ %s ] |> Maybe.map .readingsSince) == Just 0" % (fold, seen),
        ])
        self.assertEqual(answers, [True] * 6)

    def test_the_head_only_parse_drops_messages_and_the_clause_says_so(self):
        """#123's last Unverified item, executed rather than reasoned about.

        `parseQuickMessage` answers `Maybe` and takes the head twice over: the
        first `QuickMessage` node in the layer, and the first display text in
        that node. Both drop everything after them. A layer carrying two of
        each is run through the real parser here, so the counts the clause
        prints are the parser's own arithmetic rather than a claim about it.
        """
        answers = self.repl.evaluate(
            ["(one |> Maybe.andThen quickMessageOnScreen"
             " |> Maybe.map .messagesInLayer) == Just 1",
             "(one |> Maybe.andThen quickMessageOnScreen"
             " |> Maybe.map .displayTextsInMessage) == Just 1",
             "(two |> Maybe.andThen quickMessageOnScreen"
             " |> Maybe.map .messagesInLayer) == Just 2",
             "(two |> Maybe.andThen quickMessageOnScreen"
             " |> Maybe.map .text) == Just \"first message\"",
             "(split |> Maybe.andThen quickMessageOnScreen"
             " |> Maybe.map .displayTextsInMessage) == Just 2",
             "(split |> Maybe.andThen quickMessageOnScreen"
             " |> Maybe.map .text) == Just \"first half\"",
             "(empty |> Maybe.andThen quickMessageOnScreen) == Nothing"],
            definitions=[
                reading_binding("one", [layer_abovemain([[AWKWARD_TEXT]])]),
                reading_binding("two", [layer_abovemain(
                    [["first message"], ["second message"]])]),
                reading_binding("split", [layer_abovemain(
                    [["first half", "second half"]])]),
                reading_binding("empty", []),
            ])
        self.assertEqual(answers, [True] * 7)

        clauses = self.repl.strings(
            ["describeQuickMessage (Just "
             + sighting("m", messages=2) + ")",
             "describeQuickMessage (Just "
             + sighting("m", display_texts=3) + ")",
             "describeQuickMessage (Just " + sighting("m") + ")"])
        self.assertIn("1 of 2", clauses[0])
        self.assertIn("1 of 3", clauses[1])
        self.assertNotIn("1 of", clauses[2],
                         "a layer holding one message has nothing to report "
                         "about dropped ones")

    def test_a_message_read_off_a_real_tree_reaches_the_clause_intact(self):
        """End to end: UI tree, real parser, memory rule, printed clause.

        Each half is asserted above; this is the one case that runs the whole
        path, because a break in the wiring between them would leave every other
        case passing.
        """
        [clause] = self.repl.strings(
            ["describeQuickMessage"
             " (quickMessageAfterReading"
             " { onScreenNow = (one |> Maybe.andThen quickMessageOnScreen)"
             ", before = Nothing })"],
            definitions=[
                reading_binding("one", [layer_abovemain([[AWKWARD_TEXT]])])])
        self.assertIn(AWKWARD_TEXT, clause)
        self.assertIn(self.LIVE_MARKER, clause)

    def test_nothing_decides_anything_on_the_carried_forward_message(self):
        """The scope of #123, and since #146 the line between two fields.

        Logging first and matching later was the whole argument, and the corpus
        it produced is what #146's drone-launch rule is written against. What
        survives unchanged is which *field* a decision may read. The memory
        field is the sighting carried forward with an age, and it is read in
        exactly two places -- the update that writes it and the status line that
        prints it. A rule reading it would learn from a popup shown before the
        last dock, which is why #146 reads `quickMessageOnScreen` instead and
        refuses an aged sighting inside its own matcher. Both fields type-check
        at that call site, so a third reader appearing here is the mistake this
        case exists to catch.
        """
        declarations = top_level_declarations(source_of(self.BOT_ELM))
        readers = sorted(
            name for name, body in declarations.items()
            if re.search(r"[Mm]emory[a-zA-Z]*\.quickMessage\b", body))
        self.assertEqual(
            readers,
            ["statusTextFromState", "updateMemoryForNewReadingFromGame"],
            "something other than the memory update and the status line is "
            "reading the quick message -- #123 is about recording the wording, "
            "and a matcher on a wording nobody has seen is what it exists to "
            "avoid")

        self.assertIn("describeQuickMessage", declarations,
                      "the clause itself has gone, so the check below would "
                      "pass having found nothing")
        callers = sorted(
            name for name, body in declarations.items()
            if name != "describeQuickMessage"
            and re.search(r"\bdescribeQuickMessage\b", body))
        self.assertEqual(callers, ["statusTextFromState"])

    def test_the_clause_is_printed_on_every_reading_not_only_in_space(self):
        """Placed outside the ship-UI case, which is where this could be lost.

        `describeCurrentReading` is only built when a reading has a ship UI, and
        a docked reading is exactly where a client notice nobody has read is
        most likely to be sitting. So the clause is a line of its own in the
        outer list.
        """
        status = collapsed(
            declaration(source_of(self.BOT_ELM), "statusTextFromState"))
        self.assertIn("[ describeQuickMessage context.memory.quickMessage ]",
                      status)
        self.assertNotIn(
            "describeCurrentReading = describeQuickMessage", status)

        # The clause has to sit outside the `case ... shipUI of` that builds
        # `describeCurrentReading`, which the outer list is what guarantees.
        outer = status.split("in [ ")[-1]
        self.assertIn("describeQuickMessage", outer,
                      "the clause is not in the list the status line is "
                      "assembled from, so a docked reading would not carry it")

    def test_the_memory_update_ages_the_sighting_every_reading(self):
        """The counter and the clause are the same rule, on every reading.

        `updateMemoryForNewReadingFromGame` runs unconditionally, which is what
        makes an age printed beside a message mean readings rather than
        something the decision tree happened to reach.
        """
        update = collapsed(
            declaration(source_of(self.BOT_ELM),
                        "updateMemoryForNewReadingFromGame"))
        self.assertIn("quickMessage = quickMessageAfterReading", update)
        self.assertIn(
            "onScreenNow = quickMessageOnScreen context.readingFromGameClient",
            update)
        self.assertIn("before = botMemoryBefore.quickMessage", update)


class MissionRunnerQuickMessageTest(QuickMessageCases, unittest.TestCase):
    REPL_CLASS = MissionRunnerRepl
    BOT_ELM = MISSION_RUNNER_BOT_ELM
    LIVE_MARKER = "(on screen now)"
    STALE_MARKER = "NOT on screen now"


class SaxratQuickMessageTest(QuickMessageCases, unittest.TestCase):
    REPL_CLASS = SaxratRepl
    BOT_ELM = SAXRAT_BOT_ELM
    LIVE_MARKER = "(now)"
    STALE_MARKER = "ago)"


class BothAppsRecordTheSameThing(unittest.TestCase):
    """The two copies of the rules, which are the same and have to stay so.

    `ParseUserInterface.elm` is vendored per app and the policy is that a change
    lands in every copy identically; the same argument applies to a rule reading
    one of its fields. The status *line* differs between the apps deliberately
    -- their conventions do, and since #242 so does the clause's own wording --
    so what is compared here is the rules and not what is printed from them,
    which the case below takes on separately.

    Nothing here needs `elm`.
    """

    # What the message is, when it was seen, and how it is cut down to one line:
    # the three questions #123 is about, and the three rules that answer them.
    # A drift in any of these is a drift in what gets recorded.
    SHARED_RULES = [
        "quickMessageOnScreen",
        "quickMessageAfterReading",
        "quickMessageTextForStatusLine",
    ]

    def rules(self, path):
        return {name: collapsed(declaration(source_of(path), name))
                for name in self.SHARED_RULES}

    def test_the_rules_are_identical_in_both_apps(self):
        self.assertEqual(self.rules(MISSION_RUNNER_BOT_ELM),
                         self.rules(SAXRAT_BOT_ELM))

    def test_only_the_rendering_diverges_and_it_diverges_one_way(self):
        """`describeQuickMessage` is the one that is deliberately not shared.

        #242 shortened saxrat's status line and left the mission runner's alone,
        so the same sighting reads `Quick msg (now)` in one app and
        `Quick message (on screen now)` in the other, and saxrat drops a message
        older than `quickMessageStaleAfterReadings` rather than reprinting it
        beside a reading it has nothing to do with. That is a decision about one
        bot's log rather than about what either bot records, which is why the
        three rules above are still compared and this one is not.

        What is asserted is the *shape* of the divergence, so that a rendering
        drifting for any other reason -- or the cutoff appearing in the mission
        runner without anyone deciding to put it there -- is a failure rather
        than something this case quietly permits.
        """
        mission = source_of(MISSION_RUNNER_BOT_ELM)
        saxrat = source_of(SAXRAT_BOT_ELM)

        self.assertNotEqual(
            collapsed(declaration(mission, "describeQuickMessage")),
            collapsed(declaration(saxrat, "describeQuickMessage")),
            "the two clauses now read the same, so this case is asserting a "
            "divergence that is over -- compare the rendering with the rest of "
            "the rules again instead")

        self.assertIn("quickMessageStaleAfterReadings",
                      collapsed(declaration(saxrat, "describeQuickMessage")))
        self.assertEqual(
            source_of(MISSION_RUNNER_BOT_ELM).count(
                "quickMessageStaleAfterReadings"), 0,
            "the mission runner has grown saxrat's staleness cutoff -- if that "
            "is wanted then say so here, since a message dropped from the "
            "status line is one an operator cannot read beside the decision "
            "that followed it")

        # Both still say the same things about the message itself, whatever
        # words they say them in.
        for path in (MISSION_RUNNER_BOT_ELM, SAXRAT_BOT_ELM):
            with self.subTest(app=os.path.basename(os.path.dirname(path))):
                clause = collapsed(
                    declaration(source_of(path), "describeQuickMessage"))
                self.assertIn("quickMessageTextForStatusLine seen.text", clause)
                self.assertIn("String.fromInt seen.readingsSince", clause)
                self.assertIn("quickMessageStatusCharacterBudget", clause)
                self.assertIn("seen.messagesInLayer", clause)
                self.assertIn("seen.displayTextsInMessage", clause)

    def test_both_apps_cap_at_the_same_length(self):
        mission = integer_constant(source_of(MISSION_RUNNER_BOT_ELM),
                                   "quickMessageStatusCharacterBudget")
        saxrat = integer_constant(source_of(SAXRAT_BOT_ELM),
                                  "quickMessageStatusCharacterBudget")
        self.assertEqual(mission, saxrat)
        self.assertEqual(mission, EXPECTED_BUDGET)

    def test_exactly_one_matcher_reads_the_message_and_it_is_named(self):
        """#92's trap, refused in the place it would be introduced.

        A rule keyed on words nobody has read was the failure #123 was ordered
        to avoid, and #146 lifted that only for the one message it measured
        against the whole recorded vocabulary. What must not happen next is a
        second matcher appearing without that work being repeated -- the
        vocabulary grows, and this corpus already contains a message meaning
        success in progress (`automatic approach`) and a dozen that are pure
        narration.

        So the boundary is counted rather than described: exactly one
        declaration per app takes a `QuickMessageSighting` and compares its
        text, and its name is stated here. A second one fails this case, which
        is the point at which somebody has to argue for it.
        """
        for path in (MISSION_RUNNER_BOT_ELM, SAXRAT_BOT_ELM):
            with self.subTest(app=os.path.basename(os.path.dirname(path))):
                declarations = top_level_declarations(source_of(path))
                matchers = sorted(
                    name for name, body in declarations.items()
                    if "QuickMessageSighting" in body
                    and "stringContainsIgnoringCase" in body)
                self.assertEqual(
                    matchers, ["droneLaunchRefusalStatedInQuickMessage"],
                    "the set of rules matching on the quick message's wording "
                    "is %r rather than the one #146 argued for" % matchers)

                # And that one compares against named constants rather than a
                # literal written where it is used, so the corpus check in
                # `test_drone_launch_refusal.py` can read the strings the bot
                # actually ships and run them against the client's own lines.
                body = collapsed(
                    declarations["droneLaunchRefusalStatedInQuickMessage"])
                self.assertEqual(
                    re.findall(r'stringContainsIgnoringCase "', body), [],
                    "the drone-launch matcher compares against a literal "
                    "written in place, so nothing can check it against the "
                    "recorded wordings")
