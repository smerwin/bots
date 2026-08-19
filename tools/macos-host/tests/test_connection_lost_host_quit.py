"""Tests for the host quitting a client that has lost its connection.

Issue #299. A client showing

    Connection Lost
    Connection to server was lost.
    For advice on possible troubleshooting please see here.
                      [ Quit ]

sits there forever, holding the install open so the launcher cannot patch. One
launched 15:38 on 16 Aug was still there the next morning, having slept through
downtime. Nothing dismissed it: since #185 the bot answers
`LeaveTheMessageBoxAlone` at this box *deliberately*, because every control on
it quits the client and #54's standing rule is that the automatic reply
declines. So it needed a person with `Stop-Process` -- and **a kill is worse
than a click**, because EVE writes its window layout on a clean exit. The killed
client came back with the probe scanner closed, so a run launched expecting it
open could not hunt at all, and with the info panels in the state that then met
#297's deadlock. Both were investigated as fresh bugs before the cause was
understood.

**The host is the actor, so #54's rule is not touched.** No affirmative goes
near `closeMessageBoxByDeclining`, and a case here asserts the Elm side is
exactly as #185 left it: the bot goes on leaving the box alone, and the host
quits the client out from under it.

**The trigger is the box, not `ReadCompletionWatch`.** #299 offered the
reads-not-completing threshold as the hook. The corpus refuses it, and
`TheTriggerIsTheBoxAndNotTheReadCount` recounts why.

Nothing here reads a live game client or drives any input. The trees are built
by the same `message_box_tree` the Elm cases use, so what the host is asked
about is a tree the real `EveOnline.ParseUserInterface` is known to turn into
one `MessageBox`.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlab_host"))

from botlab_host import (  # noqa: E402
    CONNECTION_LOST_ABSENT, CONNECTION_LOST_NO_CONTROL, CONNECTION_LOST_QUIT_AT,
    CONNECTION_LOST_READINGS_BEFORE_QUIT, ConnectionLostWatch,
    connection_lost_quit_point, display_texts_in, find_connection_lost_box,
    node_display_text, walk_with_regions)

from prerequisites import EVE_BOT_LOGS  # noqa: E402
from test_saxrat_ported_guards import (  # noqa: E402
    SAXRAT_BOT_ELM, body_of, collapsed, label, node, source_of, tree_with)
from test_saxrat_message_box_standoff import (  # noqa: E402
    MISSION_RUNNER_BOT_ELM, message_box_tree)

# The box, as all four recorded instances printed it. `Quit` first because it is
# a button label and the identity joins every display text in order.
CONNECTION_LOST = ["Quit", "Connection Lost", "Connection to server was lost.<br>"]

# The *other* box titled `Connection Lost`, off `saxrat_run15.log`. One OK, and
# a body that says the connection was closed rather than lost. Deliberately not
# matched: its wording was never walked and its button is not the Quit this
# clicks, so quitting a client on it would be acting on a title alone.
CONNECTION_CLOSED = ["OK", "Connection Lost",
                     "The connection to the server was closed.<br>"]

# Boxes that must never be read as this one.
ORDINARY_BOXES = [
    (["Warning", "Are you sure you want to undock?"],
     [("no_dialog_button", "No"), (None, "Yes")]),
    (["Notification", "Your ship has been repaired."], [(None, "OK")]),
    (["Quit Mission?", "Are you sure you want to quit this mission?"],
     [("no_dialog_button", "No"), (None, "Yes")]),
]

# Each says only one half of the pair, so neither is this box.
HALF_MATCHES = [
    ["Connection Lost"],
    ["Connection to server was lost."],
    ["Quit", "Lost", "connection"],
]


def tree_showing(texts, buttons=((None, "Quit"),), origin=(300, 200)):
    return tree_with([message_box_tree(list(texts), list(buttons), origin=origin)])


def nested_box(origin, quit_parent_region=(0, 0, 80, 24)):
    """The box with every region inside it written relative to its parent.

    `message_box_tree` writes each node's region already offset by the origin it
    was given, which is harmless -- the Elm parser and this host accumulate it
    the same way -- but it means moving that origin moves every stored number at
    once, so it cannot tell an inherited offset from a node's own. This one
    moves only the outermost region, which is what the arithmetic turns on.

    `quit_parent_region` is `None` for a button carrying no region at all.
    """
    left, top = origin
    button_children = [label("Quit", (4, 4, 70, 16))]
    button = (node("Button", {}, button_children, region=quit_parent_region)
              if quit_parent_region is not None
              else node("Button", {}, button_children))
    return tree_with([node("MessageBox", {}, [
        label("Connection Lost", (10, 10, 200, 16)),
        label("Connection to server was lost.", (10, 30, 200, 16)),
        node("ButtonGroup", {}, [button], region=(10, 120, 300, 24)),
    ], region=(left, top, 400, 200))])


class TheBoxIsRecognisedByTheClientsOwnWords(unittest.TestCase):

    def verdict(self, texts, buttons=((None, "Quit"),)):
        return connection_lost_quit_point(tree_showing(texts, buttons))[0]

    def test_the_recorded_box_is_recognised(self):
        self.assertEqual(CONNECTION_LOST_QUIT_AT, self.verdict(CONNECTION_LOST))

    def test_the_wording_is_matched_whatever_its_case(self):
        self.assertEqual(
            CONNECTION_LOST_QUIT_AT,
            self.verdict([text.upper() for text in CONNECTION_LOST],
                         [(None, "QUIT")]))

    def test_ordinary_boxes_are_not(self):
        for texts, buttons in ORDINARY_BOXES:
            with self.subTest(texts[0]):
                self.assertEqual(
                    CONNECTION_LOST_ABSENT, self.verdict(texts, buttons),
                    "an ordinary dialog read as the connection being lost would"
                    " quit a client with a live session in it")

    def test_half_a_match_is_not_a_match(self):
        for texts in HALF_MATCHES:
            with self.subTest(texts):
                self.assertEqual(
                    CONNECTION_LOST_ABSENT, self.verdict(texts),
                    "one substring is not the pair -- a single common word"
                    " reaches dialogs this must not quit a client at")

    def test_the_other_connection_lost_box_is_not_this_one(self):
        """`saxrat_run15.log`'s box, which shares only the title."""
        self.assertEqual(
            CONNECTION_LOST_ABSENT,
            self.verdict(CONNECTION_CLOSED, [(None, "OK")]),
            "the run 15 box was never walked and offers OK rather than Quit, so"
            " matching it would be quitting a client on a title alone")

    def test_a_node_that_is_not_a_message_box_is_not_one(self):
        """The words alone are not the box.

        The wording can appear in something that is not a modal at all -- a chat
        line, a notification, the client's own log window. What four recorded
        runs establish is that this dialog parses as a `MessageBox`, which is
        the only thing `parseMessageBoxesFromUITreeRoot` accepts, so that is
        asked for as well as the words.
        """
        impostor = node("Container", {},
                        [label(text, (310, 210 + index * 20, 200, 16))
                         for index, text in enumerate(CONNECTION_LOST)],
                        region=(300, 200, 400, 200))
        self.assertEqual(
            CONNECTION_LOST_ABSENT,
            connection_lost_quit_point(tree_with([impostor]))[0])

    def test_the_box_is_found_among_other_windows(self):
        other, _ = ORDINARY_BOXES[1]
        tree = tree_with([
            message_box_tree(other, [(None, "OK")], origin=(50, 50)),
            message_box_tree(CONNECTION_LOST, [(None, "Quit")], origin=(300, 200)),
        ])
        self.assertEqual(CONNECTION_LOST_QUIT_AT,
                         connection_lost_quit_point(tree)[0])


class WhereItAims(unittest.TestCase):
    """The point, which is the part the recorded runs cannot settle."""

    def point(self, origin):
        verdict, point = connection_lost_quit_point(
            tree_showing(CONNECTION_LOST, origin=origin))
        self.assertEqual(CONNECTION_LOST_QUIT_AT, verdict)
        return point

    def test_it_aims_inside_the_control_reading_quit(self):
        box = find_connection_lost_box(tree_showing(CONNECTION_LOST))
        self.assertIsNotNone(box)
        quit_regions = [
            (x, y, width, height)
            for node_, x, y, width, height in walk_with_regions(*box)
            if (node_display_text(node_) or "").strip().lower() == "quit"]
        self.assertTrue(quit_regions, "the fixture has no Quit control")
        x, y, width, height = quit_regions[0]
        point = self.point((300, 200))
        self.assertTrue(
            x <= point[0] <= x + width and y <= point[1] <= y + height,
            "%s is not inside the control reading Quit at %s"
            % (point, (x, y, width, height)))

    def test_moving_the_whole_box_moves_the_point_with_it(self):
        """The offsets are inherited, not read off one node.

        `_displayX`/`_displayY` are relative to the parent, so a point taken
        from the button alone would be the same wherever the dialog sat -- and
        the click would land somewhere else entirely on any layout but the one
        it was derived on. Only the box's own origin moves between these two
        trees; every region inside it is written identically.
        """
        for left, top in [(300, 200), (700, 500)]:
            with self.subTest((left, top)):
                verdict, point = connection_lost_quit_point(
                    nested_box((left, top)))
                self.assertEqual(CONNECTION_LOST_QUIT_AT, verdict)
                # 10 (group) + 0 (button) + 4 (label) + half of 70x16.
                self.assertEqual(
                    (left + 10 + 0 + 4 + 35, top + 120 + 0 + 4 + 8), point)


class ItFailsToNothingRatherThanToAGuess(unittest.TestCase):
    """The shape has never been walked, so the matcher has to survive being wrong.

    What the corpus establishes is that the box parses as a `MessageBox` and
    that `Quit` is among its display texts. What node carries that text, and
    what the button's `_name` is, are unknown -- `messageBoxIdentityForOperator`
    truncates before the `with buttons [...]` section in every recorded
    instance. So a tree that does not hold what is expected must click nothing.
    """

    def test_a_box_with_no_quit_control_is_not_clicked(self):
        verdict, point = connection_lost_quit_point(
            tree_showing(["Connection Lost", "Connection to server was lost."],
                         [(None, "Dismiss")]))
        self.assertEqual(CONNECTION_LOST_NO_CONTROL, verdict)
        self.assertIsNone(point)

    def test_a_quit_behind_an_unplaced_ancestor_is_not_clicked(self):
        """A placed label under an unplaced parent is still not a place on screen.

        Its `_displayX`/`_displayY` are relative to a parent that has no
        position, so the sum has no meaning -- and this is what the Elm side
        sees too: `listDescendantsWithDisplayRegion` stops at a node with no
        region and never reaches what is under it, so a subtree skipped here is
        one the bot never had a coordinate for either.
        """
        verdict, point = connection_lost_quit_point(
            nested_box((300, 200), quit_parent_region=None))
        self.assertEqual(CONNECTION_LOST_NO_CONTROL, verdict)
        self.assertIsNone(point)

    def test_a_zero_sized_quit_is_not_clicked(self):
        box = node("MessageBox", {}, [
            label("Connection Lost", (310, 210, 200, 16)),
            label("Connection to server was lost.", (310, 230, 200, 16)),
            label("Quit", (310, 320, 0, 0)),
        ], region=(300, 200, 400, 200))
        self.assertEqual(CONNECTION_LOST_NO_CONTROL,
                         connection_lost_quit_point(tree_with([box]))[0])

    def test_an_empty_tree_says_absent_rather_than_raising(self):
        for tree in [{}, {"children": []}, tree_with([])]:
            with self.subTest(tree):
                self.assertEqual((CONNECTION_LOST_ABSENT, None),
                                 connection_lost_quit_point(tree))


class HowItReadsANode(unittest.TestCase):
    """`getDisplayText`'s rule, which this reimplements in Python."""

    def test_the_longest_of_the_two_text_properties_wins(self):
        self.assertEqual("the longer one", node_display_text(node(
            "X", {"_setText": "short", "_text": "the longer one"})))

    def test_text_nested_one_level_down_is_still_text(self):
        """EVE puts info-panel text inside a `Link` object rather than a string,
        which the Elm decoder already had to reach through."""
        self.assertEqual("Quit", node_display_text(node(
            "X", {"_setText": node("Link", {"_text": "Quit"})})))

    def test_a_node_with_no_text_has_none(self):
        self.assertIsNone(node_display_text(node("X", {"_name": "not text"})))

    def test_the_texts_of_a_subtree_are_every_descendants(self):
        tree = node("A", {"_setText": "one"},
                    [node("B", {"_text": "two"},
                          [node("C", {"_setText": "three"})])])
        self.assertEqual({"one", "two", "three"}, set(display_texts_in(tree)))

    def test_a_region_less_node_does_not_hide_text_from_the_wording_match(self):
        """The words are read off the raw subtree, unlike the click point.

        `parseMessageBox` asks `getAllContainedDisplayTexts`, which walks the
        unparsed node -- so a box whose text sits under an unplaced container is
        still recognised, even though nothing in it can be clicked.
        """
        box = node("MessageBox", {}, [node("Container", {}, [
            label("Connection Lost", (310, 210, 200, 16)),
            label("Connection to server was lost.", (310, 230, 200, 16)),
        ])], region=(300, 200, 400, 200))
        self.assertEqual(CONNECTION_LOST_NO_CONTROL,
                         connection_lost_quit_point(tree_with([box]))[0])


class WhenItClicks(unittest.TestCase):

    def setUp(self):
        self.watch = ConnectionLostWatch(
            before_quit=3, between_clicks=5, max_clicks=2)

    def readings(self, count, verdict=CONNECTION_LOST_QUIT_AT, point=(10, 20)):
        return [self.watch.note(verdict, point) for _ in range(count)]

    def clicks(self, notes):
        return [click for click, _ in notes if click is not None]

    def lines(self, notes):
        return [line for _, line in notes if line is not None]

    def test_one_reading_does_not_click(self):
        """A half-built tree is not a client that has lost its connection."""
        self.assertEqual([], self.clicks(self.readings(1)))

    def test_the_threshold_is_where_it_clicks(self):
        notes = self.readings(3)
        self.assertEqual([], self.clicks(notes[:2]))
        self.assertEqual([(10, 20)], self.clicks(notes[2:]))

    def test_it_does_not_click_on_every_reading_after_that(self):
        self.assertEqual(1, len(self.clicks(self.readings(7))))

    def test_it_clicks_again_once_the_first_has_had_time_to_land(self):
        """A posted click can legitimately not land -- `_windows_input` stands
        down after a person touches the mouse, and aborts if the window is not
        frontmost."""
        self.assertEqual([(10, 20), (10, 20)], self.clicks(self.readings(9)))

    def test_the_attempts_are_bounded_and_the_give_up_says_so(self):
        notes = self.readings(60)
        self.assertEqual(2, len(self.clicks(notes)))
        given_up = [line for line in self.lines(notes) if "WILL NOT TAKE" in line]
        self.assertEqual(1, len(given_up), self.lines(notes))
        self.assertIn("Not killing it", given_up[0])

    def test_it_never_escalates_to_killing_the_client(self):
        """The kill is the harm #299 is about, not its fallback of last resort.

        A killed client came back with the probe scanner closed and the info
        panels in #297's state, and both were investigated as fresh bugs. Until
        a click has been observed to work even once, automating the kill would
        ship the failure this issue was filed to stop.
        """
        printed = " ".join(self.lines(self.readings(200))).lower()
        for word in ["kill the", "terminate", "sigkill", "stop-process"]:
            self.assertNotIn(word, printed)

    def test_the_line_says_what_it_is_doing_and_why(self):
        line = [line for line in self.lines(self.readings(3)) if line][0]
        self.assertIn("CONNECTION LOST", line)
        self.assertIn("launcher", line)
        self.assertIn("layout", line)

    def test_a_box_that_goes_away_resets_the_count(self):
        """A second incident gets its own attempts, and its own threshold.

        The count is per box rather than per session: a client that reconnected
        and lost the connection again is a fresh dialog, and a watch that
        carried the first incident's tally would either click at the very first
        reading of the second or have given up on it before it appeared.
        """
        self.assertEqual(1, len(self.clicks(self.readings(3))))
        gone = self.watch.note(CONNECTION_LOST_ABSENT, None)
        self.assertIsNone(gone[0])
        self.assertIn("GONE", gone[1])
        again = self.readings(3)
        self.assertEqual([], self.clicks(again[:2]),
                         "the second incident clicked before its own threshold")
        self.assertEqual([(10, 20)], self.clicks(again[2:]),
                         "the second incident never got a click of its own")

    def test_a_run_that_never_sees_the_box_says_nothing_at_all(self):
        notes = [self.watch.note(CONNECTION_LOST_ABSENT, None) for _ in range(500)]
        self.assertEqual([(None, None)] * 500, notes)

    def test_a_box_it_cannot_aim_at_is_announced_once_and_never_clicked(self):
        notes = [self.watch.note(CONNECTION_LOST_NO_CONTROL, None)
                 for _ in range(100)]
        self.assertEqual([], self.clicks(notes))
        spoken = self.lines(notes)
        self.assertEqual(1, len(spoken), spoken)
        self.assertIn("NOTHING TO CLICK", spoken[0])

    def test_the_shipped_threshold_is_a_few_readings_and_not_a_few_hundred(self):
        """The default is a judgement and is worth pinning as one.

        In all four recorded instances the box was still on screen at the last
        reading of the log, so it has never once cleared on its own: waiting
        buys nothing, and every reading waited is another minute of an install
        the launcher cannot patch.
        """
        self.assertGreater(CONNECTION_LOST_READINGS_BEFORE_QUIT, 1)
        self.assertLess(CONNECTION_LOST_READINGS_BEFORE_QUIT, 30)


class TheTriggerIsTheBoxAndNotTheReadCount(unittest.TestCase):
    """#299 offered `ReadCompletionWatch`'s threshold as the hook. It is wrong.

    Three independent reasons, each recounted below against the corpus:

      * the box does not stop reads completing -- `saxrat_run40.log` held it for
        **1199 consecutive readings**, every one a completed read carrying the
        box's own wording, because a read here is `tree_walker` walking the
        client's address space rather than a request the client answers;
      * `READS ARE NOT COMPLETING` appears in **no** recorded run at all, this
        dialog's four included;
      * and run 11, the stall #164 was filed about, was reads *issued and never
        answered* -- `read_failure_reason` only counts a result that came back
        carrying an `Err`, which those never did.

    So the counter is neither necessary nor sufficient, and the dialog is the
    positive evidence the issue asked for. `ConnectionLostWatch` is fed the
    reading and nothing else, which the first case here pins.
    """

    def test_the_watch_is_fed_the_box_and_nothing_else(self):
        watch = ConnectionLostWatch(before_quit=1)
        self.assertEqual((None, None), watch.note(CONNECTION_LOST_ABSENT, None))
        click, _ = watch.note(CONNECTION_LOST_QUIT_AT, (1, 2))
        self.assertEqual((1, 2), click,
                         "the decision must rest on the reading it was handed")

    def test_the_read_completion_watch_still_takes_no_action(self):
        """#166's counter is a diagnostic and this change leaves it one."""
        from botlab_host import ReadCompletionWatch
        watch = ReadCompletionWatch(threshold=1)
        self.assertIsInstance(watch.note("the client did not answer"), str)
        self.assertFalse(
            hasattr(watch, "click") or hasattr(watch, "quit"),
            "the reads-not-completing counter has grown an action, which is the"
            " trigger the corpus refuses")


class TheReadingIsWhatFeedsIt(unittest.TestCase):
    """The wiring, which no amount of testing the rule reaches.

    A watch counted in readings has to be handed exactly one reading per read
    that completed. Fed from the outer loop instead it would advance on every
    screenshot and input task as well, and the threshold would mean a different
    number of readings depending on what the bot happened to be doing.
    """

    def test_a_verdict_is_taken_once_and_then_gone(self):
        from botlab_host import VolatileHost
        host = VolatileHost.__new__(VolatileHost)
        host._connection_lost = (CONNECTION_LOST_QUIT_AT, (1, 2))
        self.assertEqual((CONNECTION_LOST_QUIT_AT, (1, 2)),
                         host.take_connection_lost())
        self.assertIsNone(
            host.take_connection_lost(),
            "a second task in the same tick would be counted as a second"
            " reading of a box nothing read again")

    def test_the_loop_takes_it_and_acts_on_it(self):
        source = source_of(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "botlab_host", "botlab_host.py"))
        for call in ["ConnectionLostWatch()",
                     "dispatcher.volatile.take_connection_lost()",
                     "connection_lost_watch.note(",
                     "dispatcher.click_connection_lost_quit("]:
            self.assertIn(call, source,
                          "the host no longer reaches %s, so the box is"
                          " recognised and nothing happens" % call)

    def test_the_verdict_is_taken_before_the_synthetic_nodes_are_added(self):
        """What is judged has to be what the client is drawing.

        `_read_from_window` appends the game log and damage nodes to the tree it
        hands back. They carry no display region and no `MessageBox`, so the
        answer would not change -- but a reading that says the client is showing
        a modal must be about the client and not about anything this host put
        in the tree.
        """
        source = source_of(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "botlab_host", "botlab_host.py"))
        body = source[source.index("def _read_from_window"):]
        body = body[:body.index("\n    def ")]
        self.assertLess(
            body.index("self._connection_lost = connection_lost_quit_point"),
            body.index("synthetic_game_log_node"))


class TheBotStillLeavesTheBoxAlone(unittest.TestCase):
    """#54's standing rule, which this change must not have loosened.

    The host is the actor precisely so that it need not be. Three places already
    assert the declining reply; these two say the same thing from this side, so
    a later change that moved the quit into `Bot.elm` cannot do it quietly.
    """

    APPS = {"saxrat": SAXRAT_BOT_ELM, "mission runner": MISSION_RUNNER_BOT_ELM}

    def test_the_declining_answer_still_contains_no_affirmative(self):
        for app, path in self.APPS.items():
            branch = collapsed(body_of(source_of(path),
                                       "closeMessageBoxByDeclining"))
            for affirmative in ('"yes"', "yes_dialog_button"):
                self.assertNotIn(affirmative, branch.lower(), app)

    def test_the_bot_still_leaves_this_box_alone(self):
        for app, path in self.APPS.items():
            branch = collapsed(body_of(source_of(path),
                                       "messageBoxStandoffVerdictForBox"))
            self.assertIn("messageBoxSaysTheConnectionIsLost", branch, app)
            self.assertIn("LeaveTheMessageBoxAlone", branch, app)

    def test_the_wording_the_host_matches_is_the_wording_the_bot_matches(self):
        """A cross-language coupling, pinned rather than remembered.

        Both sides recognise this box by the same two substrings, read off the
        same recorded instances. A rewording on one side only would leave the
        bot leaving a box alone that the host no longer quits -- the exact state
        #299 was filed about, restored silently.
        """
        from botlab_host import CONNECTION_LOST_WORDING
        for app, path in self.APPS.items():
            branch = collapsed(body_of(source_of(path),
                                       "messageBoxSaysTheConnectionIsLost"))
            for half in CONNECTION_LOST_WORDING:
                self.assertIn('"%s"' % half, branch, app)


def saxrat_runs():
    found = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
    if not found:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs can"
            " say about the Connection Lost incident cannot be consulted here")
    return found


class TheCorpusIsWhatRefusesTheReadCountTrigger(unittest.TestCase):
    """The recount, so the reasoning above is checked rather than asserted."""

    @staticmethod
    def _text(path):
        with open(path, errors="replace") as handle:
            return handle.read()

    def test_no_recorded_run_ever_said_reads_were_not_completing(self):
        said = [os.path.basename(path) for path in saxrat_runs()
                if "READS ARE NOT COMPLETING" in self._text(path)]
        self.assertEqual(
            [], said,
            "a run does carry the reads-not-completing line, so the claim that"
            " the counter has never fired needs re-deriving before it is used"
            " to argue this trigger")

    def test_the_runs_that_met_this_box_kept_reading_the_client(self):
        met = []
        for path in saxrat_runs():
            text = self._text(path)
            if "Connection to server was lost" not in text:
                continue
            met.append(os.path.basename(path))
            self.assertNotIn(
                "READS ARE NOT COMPLETING", text,
                "%s met this box *and* stopped completing reads, so the box is"
                " not visible while it happens and the host cannot be the actor"
                % os.path.basename(path))
        self.assertTrue(
            met,
            "no recorded run carries the Connection Lost box, so the corpus no"
            " longer evidences the dialog this exists to quit")

    def test_a_run_held_the_box_for_hundreds_of_readings(self):
        """The positive form: the box is on screen, and readable, for a long time.

        `saxrat_run40.log` counted it to 1199 -- and the log ends with the box
        still up, which is the state #299 is about.
        """
        held = []
        for path in saxrat_runs():
            for line in self._text(path).splitlines():
                if "Connection to server was lost" not in line:
                    continue
                before, _, after = line.partition("Message box: ")
                if not after:
                    continue
                count = after.split("/")[0]
                if count.isdigit():
                    held.append(int(count))
        self.assertTrue(held, "no run's status clause counted this box at all")
        self.assertGreater(
            max(held), 100,
            "no recorded run held this box for more than 100 readings, so the"
            " claim that it never clears on its own needs re-deriving")


if __name__ == "__main__":
    unittest.main()
