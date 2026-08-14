"""Tests for the client's own stated lock range outranking the learned bound.

Issue #206. `lockProvenAtMeters` only ever rises, so an attribution error that
credits a lock to a more distant row is **permanent**: run 28 ratcheted to 77 km
on a hull whose real lock range is 49 km, while `lockRefusedAtMeters` fell to
33 km. The two crossed -- proven 77 km above refused 33 km is the bot holding
contradictory evidence about one hull -- and `lockRangeThresholdInMeters`
resolved that in favour of proven, so `targeting-range=49000` sat inert and only
a restart could clear it.

The client had answered the question outright, in words, and named the number:

    The target <b>Centii Minion</b> is too far away. It must be within <b>49 km</b>.

1,277 live sightings of that sentence in run 28 alone -- the run whose own bound
climbed to 77 km. That is `quickMessage`'s documented shape: evidence that
arrived, was decoded, and was thrown away.

Two things the cases below are careful about:

- **The ceiling is not a constant.** Only 49 km and 39 km occur across the
  corpus, and runs 13 and 14 carry both within one session -- a sensor booster
  is the obvious candidate. So the stated value is *overwritten*, never
  narrowed: another monotone bound here would be #206 again in the other
  direction.
- **The sentence has to be read as a pair.** "too far away" alone is written
  about warping, approaching and interacting; only its pairing with a stated
  ceiling makes it about the lock range. #31's reason, and a case pins it.

The rules are executed through the real `Bot.elm` in `elm repl`.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, REPO_DIR, open_repl

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")

PREAMBLE = ("import Bot exposing (..)",)

# Verbatim from the corpus, markup included.
STATED = ("The target <b>Centii Minion</b> is too far away."
          " It must be within <b>49 km</b>.")

# Run 28's end state: the ratchet, its crossed refusal, and the setting it made
# inert.
RUN_28 = {"setting": 49000, "proven": 77000, "refused": 33000, "stated": 49000}


class SaxratRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-lockstated-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


def elm_string(value):
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def state(setting, stated=None, proven=None, refused=None):
    def maybe(v):
        return "Nothing" if v is None else "Just %d" % v
    return ("{ fromSetting = %d, statedMeters = %s, provenAtMeters = %s"
            ", refusedAtMeters = %s, attempt = Nothing }"
            % (setting, maybe(stated), maybe(proven), maybe(refused)))


class TheSentenceIsReadTest(unittest.TestCase):
    """What the client wrote, turned into a number."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def stated_in(self, text):
        return self.repl.strings(
            ['(lockRangeStatedInText %s'
             ' |> Maybe.map String.fromInt |> Maybe.withDefault "none")'
             % elm_string(text)])[0]

    def test_the_corpus_sentence_gives_its_ceiling_in_meters(self):
        self.assertEqual(self.stated_in(STATED), "49000")

    def test_the_markup_is_stripped_rather_than_matched_around(self):
        """The number arrives inside `<b>` tags, as the corpus writes it."""
        self.assertEqual(
            self.stated_in("is too far away. It must be within 39 km."),
            "39000")

    def test_the_other_value_the_corpus_carries_is_read_too(self):
        """49 and 39 both occur, and runs 13 and 14 carry both in one run."""
        self.assertEqual(
            self.stated_in(STATED.replace("49 km", "39 km")), "39000")

    def test_too_far_away_without_a_ceiling_is_not_a_lock_range(self):
        """#31's pair. This sentence is written about several other things."""
        for other in [
            "You are too far away to interact with this object.",
            "The container is too far away.",
            "Your ship is too far away to warp to that.",
        ]:
            with self.subTest(other):
                self.assertEqual(self.stated_in(other), "none")

    def test_a_ceiling_without_the_refusal_is_not_read_either(self):
        self.assertEqual(
            self.stated_in("The module must be within 5 km."), "none")

    def test_a_unit_this_does_not_know_is_declined_rather_than_guessed(self):
        """A wrong guess here becomes a threshold trusted over measurements."""
        for text in [
            "is too far away. It must be within 49000 m.",
            "is too far away. It must be within 49.",
            "is too far away. It must be within lots km.",
        ]:
            with self.subTest(text):
                self.assertEqual(self.stated_in(text), "none")


class TheStatedCeilingOutranksTheRatchetTest(unittest.TestCase):
    """`lockRangeThresholdInMeters`, which is where #206 did its damage."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def threshold(self, **kwargs):
        return self.repl.strings(
            ["String.fromInt (lockRangeThresholdInMeters %s)"
             % state(**kwargs)])[0]

    def test_run_28_would_have_answered_the_setting_rather_than_77_km(self):
        """The whole issue, as the run that produced it."""
        self.assertEqual(
            self.threshold(setting=RUN_28["setting"], stated=RUN_28["stated"],
                           proven=RUN_28["proven"], refused=RUN_28["refused"]),
            "49000")

    def test_a_ratcheted_proven_cannot_raise_the_threshold_past_it(self):
        self.assertEqual(
            self.threshold(setting=66000, stated=49000, proven=77000), "49000")

    def test_a_narrower_setting_still_wins(self):
        """An operator asking for less than the ship can do is asking for
        something the client will grant, and this rule has never overridden
        that direction."""
        self.assertEqual(
            self.threshold(setting=34000, stated=49000, proven=77000), "34000")

    def test_without_a_statement_the_measurements_still_decide(self):
        """The old behaviour, unchanged where the client has said nothing."""
        self.assertEqual(self.threshold(setting=37000, proven=59000,
                                        refused=67000), "59000")
        self.assertEqual(self.threshold(setting=66000), "66000")
        self.assertEqual(self.threshold(setting=66000, refused=50000), "49999")

    def test_a_lowered_statement_lowers_the_threshold(self):
        """The booster case: 49 then 39 within one session."""
        self.assertEqual(
            self.threshold(setting=66000, stated=39000, proven=77000), "39000")


class TheStatementIsOverwrittenNotNarrowedTest(unittest.TestCase):
    """The half that keeps this from becoming another ratchet.

    Read out of the memory update rather than inferred from a name: the field is
    written from the reading when the client said something and carried forward
    when it did not, with no `min` and no `max` anywhere near it.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = re.sub(r"\s+", " ", open(SAXRAT_BOT_ELM).read())

    def test_a_new_statement_replaces_the_old_one(self):
        self.assertIn(
            "case lockRangeStatedInQuickMessage context.readingFromGameClient of"
            " Just stated -> Just stated", self.source)

    def test_a_reading_that_says_nothing_keeps_the_last_one(self):
        self.assertIn("Nothing -> botMemoryBefore.lockRangeStatedMeters",
                      self.source)

    def test_the_field_is_never_clamped_against_itself(self):
        """A `min` or `max` here is the monotone bound this exists to avoid.

        Anchored on the update's own `case`, not on the first
        `lockRangeStatedMeters =` in the file -- that one is the initialiser,
        and a window measured from it reads the fields declared after it and
        says nothing about this rule. It passed against a `min` mutation before
        being anchored, which is this repo's own vacuity trap.
        """
        start = self.source.index(
            "case lockRangeStatedInQuickMessage context.readingFromGameClient of")
        window = self.source[start:start + 300]
        self.assertNotIn("min ", window)
        self.assertNotIn("max ", window)

    def test_the_statement_is_read_from_the_live_message_not_the_echo(self):
        """The game log reprints it under every decision; counting those would
        make one refusal look like hundreds."""
        self.assertIn("lockRangeStatedInQuickMessage readingFromGameClient ="
                      " readingFromGameClient |> quickMessageOnScreen",
                      self.source)


class TheStatusClauseSaysItTest(unittest.TestCase):
    """The operator's view, which is how a wrong number gets noticed at all."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_clause_names_what_the_client_stated(self):
        [clause] = self.repl.strings(
            ["describeLockRange %s" % state(setting=66000, stated=49000,
                                            proven=77000, refused=33000)])
        self.assertEqual(
            clause,
            "lock 49000m (set 66000 client 49000 proven 77000 refused 33000 "
            "attempt none).")

    def test_an_unstated_ceiling_reads_as_absent_rather_than_as_zero(self):
        """`-` rather than `0`, which is the distinction this whole rule is.

        A ceiling nobody stated and a ceiling stated as zero are opposite
        facts -- the first leaves the setting alone and the second would refuse
        every lock -- so the clause has to keep them apart however short #242
        makes it.
        """
        [clause] = self.repl.strings(
            ["describeLockRange %s" % state(setting=66000)])
        self.assertIn("client -", clause)
        self.assertNotIn("client 0", clause)


if __name__ == "__main__":
    unittest.main()
