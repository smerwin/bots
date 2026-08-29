"""Tests for saxrat sending fleet broadcasts under `fleet-commander`.

Issue #417. saxrat reads broadcasts today (`followFleetBroadcast`,
`respondToFleetBackupBroadcast`, `fleetLastBroadcastText`) and sends none. This
is the other direction, and what makes it different from every other arm in this
bot is where the output goes: **a broadcast is read by real people**, so the
failures worth pinning are the ones that talk too much rather than the ones that
talk too little.

Four things this file exists to hold, each of them killed by a named mutation:

- **`fleet-commander` defaults to off and gates every arm.** One gate, in
  `fleetBroadcastStep`, so it cannot be half-honoured by an arm that forgot to
  ask. Removing that clause fails `TheSettingIsTheGate`.
- **A call is de-duplicated against what the client's own banner read back.**
  The banner never clears, so without this every warranted call is re-sent on
  every reading for the rest of the session. Removing the `alreadyBroadcast`
  clause fails `TheBannerIsWhatCountsAsSent`.
- **A broadcast fires from a fact the client reported, never from an
  intention.** A ship still aligning must not tell the fleet it is at location,
  and a ship taking damage must not spend the reading that saves it on saying
  so. Removing the "the client says the ship is engaged" half of the
  at-location warrant, or the "the client says the ship is in warp" half of the
  backup warrant, fails `TheWarrantsAreFactsTheClientReported`.
- **A fleet-mate's row is never clicked.** The fleet's own ships are on this
  overview, and an `Imperial Navy Slicer` row is one target call away from the
  fleet being told to shoot a friendly. Removing the pilot filter from
  `ratToCallAsTarget` fails `AFleetMateIsNeverTheTarget`.

Everything about which object a call is about is executed against readings built
by the **real** `EveOnline.ParseUserInterface`, not against source pins: the rat
row carries the client's own `myActiveTargetIndicator` and rat-coloured icon
sprite, the fleet-mate is a name in the Local userlist, and the stargate verdict
comes from the same `routeStargateJumpFromReading` the jump itself decides on.

The de-duplication and the bound are executed too, as folds of the real
`fleetBroadcastMemoryAfterReading` over readings -- which is what makes the
bound a *reachable* one rather than a comparison nothing ever reaches.

Nothing here reads a live game client, a bot, or the recorded runs. The
`elm repl` cases need `elm` on PATH; without it they **fail** rather than
skipping, for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_arrival_pilot_window import without_block_comments
from test_fleetmate_anomaly_avoidance import (FLEET_HINT, chat_user_entry,
                                              local_chat_window)
from test_saxrat_combat_stalemate import overview as combat_overview
from test_saxrat_combat_stalemate import target_in_bar
from test_saxrat_ported_guards import (SAXRAT_BOT_ELM, SaxratRepl, body_of,
                                       collapsed, node, source_of)
from test_saxrat_ported_guards import overview as plain_overview
from test_saxrat_route_ask_bound import flying
from test_saxrat_route_stargate_panel_jump import (JUMP_BUTTON,
                                                   LIVE_PANEL_NAME_LABEL,
                                                   NEXT_SYSTEM_LABEL_LIVE,
                                                   route_panel,
                                                   selected_item_window,
                                                   without_comments)
from test_saxrat_route_to_the_system_we_are_in import location_panel

# The eight fleet-window buttons, as their `_hint` reads on the live client.
# Six of them carry `_elementId = fleetwindow.<lambda>`, which is why they are
# matched on this text and not on an id -- see `FleetBroadcastVerb`.
BUTTON_HINTS = [
    "Broadcast: Spotted an Enemy",
    "Broadcast: Need Armor",
    "Broadcast: Need Shield",
    "Broadcast: Need Capacitor",
    "Broadcast: In Position at",
    "Broadcast: Need Backup",
    "Broadcast: Request That the Fleet Hold Position",
    "Broadcast: At Location",
]

# What every verb is called, keyed by its Elm constructor. The lowercase `to` in
# `Broadcast: Jump to` is the one a matcher written from the English gets wrong,
# and it would have failed silently: nothing matches, the branch never fires,
# and nothing complains.
VERB_TEXT = {
    "BroadcastNeedBackup": "Broadcast: Need Backup",
    "BroadcastJumpTo": "Broadcast: Jump to",
    "BroadcastAtLocation": "Broadcast: At Location",
    "BroadcastTarget": "Broadcast: Target",
    "BroadcastInPositionAt": "Broadcast: In Position at",
    "BroadcastSpottedAnEnemy": "Broadcast: Spotted an Enemy",
    "BroadcastNeedArmor": "Broadcast: Need Armor",
    "BroadcastNeedShield": "Broadcast: Need Shield",
    "BroadcastNeedCapacitor": "Broadcast: Need Capacitor",
    "BroadcastHoldPosition": "Broadcast: Request That the Fleet Hold Position",
    "BroadcastWarpTo": "Broadcast: Warp to",
    "BroadcastAlignTo": "Broadcast: Align to",
    "BroadcastRepairTarget": "Broadcast: Repair Target",
}

# The four sent, in the priority order `fleetBroadcastCall` reads them: the
# ship's own emergency, the gate the fleet has to follow through, arrival, then
# the primary.
VERBS_SENT = ["BroadcastNeedBackup", "BroadcastJumpTo", "BroadcastAtLocation",
              "BroadcastTarget"]

# The two entries a stargate's menu also offers and this bot does not take.
# They are not broadcasts: they move other players' ships.
FLEET_WARP_ENTRIES = ("Warp Fleet (Point)", "Warp Fleet (Point) to Within")

SYSTEM = "Safilbab"
RAT = "Centii Minion"
OTHER_RAT = "Centii Loyal Enslaver"

# A fleet-mate on grid, by the hull the capture recorded beside the rats. The
# row is a real overview row and it is *also* a name in Local, which is the
# only thing that distinguishes it from a rat.
FLEET_MATE = "Imperial Navy Slicer"

# The route's next system, and the gate row and panel label that go with it --
# all three read off the live client in #167/#170's own capture.
NEXT_SYSTEM = "Arnon"
GATE_ROW = ("8,998 m", NEXT_SYSTEM, "Stargate (CONCORD System)")
ROUTE_LABELS = ["Route <fontsize=12>5 Jumps", NEXT_SYSTEM_LABEL_LIVE]
PANEL_SHOWING_THE_GATE = (
    '%s (<color=#ff4ecef8>0.8</color>)' % NEXT_SYSTEM)

# The banner the client rendered for a target call, read back live off
# `fleetwindow.lastBroadcastBanner` after one `x` chord.
LIVE_TARGET_BANNER = "Target %s (%s)" % (RAT, RAT)

# The wordings the file already carries for the two calls whose rendered text
# *was* captured -- `fleetBackupBroadcastMarker` and
# `fleetAtLocationBroadcastMarker`.
LIVE_AT_LOCATION_BANNER = "Martha Mercoxit is at location %s" % SYSTEM
LIVE_BACKUP_BANNER = "Martha Mercoxit needs backup"

GIVE_UP_READINGS = 20

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    # `AppSettings.YesOrNo` is another module's type, and `Bot exposing (..)`
    # does not re-export another module's constructors -- so the setting cases
    # cannot name `AppSettings.No` without this. It belongs in the preamble
    # rather than in a case's `definitions`, since an `import` cannot sit in the
    # `let` those are folded into.
    "import Common.AppSettings as AppSettings",
)


def fleet_window(hints=(), banner=None):
    """The fleet window, with broadcast buttons and its persistent banner.

    Both halves are scoped inside the `FleetWindow` node on purpose:
    `fleetWindowDescendants` is what stops a `_hint` or a `bannerLabel`
    somewhere else in the tree answering for one of these, and a fixture
    without the wrapper reads as "no fleet window at all".
    """
    children = []
    for index, hint in enumerate(hints):
        children.append(node(
            "BroadcastButton",
            # The id six of the eight really carry, which is not an identifier
            # -- present in the fixture so a matcher that reached for it would
            # be matching the same useless string on every button.
            {"_hint": hint, "_elementId": "fleetwindow.<lambda>"},
            region=(186 + 36 * index, 300, 32, 32)))
    if banner is not None:
        children.append(node("FleetBroadcastCont", {"_name": "broadcastCont"}, [
            node("Container", {"_name": "lastBroadcastBanner"}, [
                node("EveLabelMedium",
                     {"_name": "bannerLabel", "_setText": banner},
                     region=(33, 1, 183, 21)),
            ], region=(0, 0, 673, 23)),
        ], region=(0, 326, 673, 87)))
    return node("FleetWindow", {"_name": "fleetwindow"}, children,
                region=(0, 0, 700, 420))


def engaged_reading(rows, users=(), banner=None, hints=(), system=SYSTEM):
    """A ship in a fight: a target on the bar, rats on the overview, Local open.

    `combatFightIsUnderway` is the client holding a lock *and* drawing rats, so
    both halves are here and either can be taken away by a caller to build the
    reading a ship still on its way produces.
    """
    children = [combat_overview(rows), location_panel(system),
                fleet_window(hints, banner), flying()]
    if users:
        children.append(local_chat_window(users))
    return children


def call_literal(identity="a call", verb="BroadcastAtLocation",
                 must_contain=('is at location',)):
    """A `FleetBroadcastCall` written out, for the cases about the step rule.

    The step function is a pure rule over a small record and is asked about
    directly, rather than through whichever warrant happens to produce one --
    so a case about de-duplication is about de-duplication.
    """
    return "{ verb = %s, identity = \"%s\", bannerMustContain = [ %s ] }" % (
        verb, identity,
        ", ".join('"%s"' % marker for marker in must_contain))


def step_expression(commander_mode=True, call=None, already=False,
                    confirms=False, asking="Nothing", asked=0, sent=0):
    call_part = "Just %s" % (call or call_literal())
    return (
        "fleetBroadcastStep"
        " { commanderMode = %s, call = %s, alreadyBroadcast = %s"
        " , bannerConfirmsTheCall = %s, asking = %s, askedReadings = %d"
        " , broadcastsSent = %d }" % (
            "True" if commander_mode else "False", call_part,
            "True" if already else "False", "True" if confirms else "False",
            asking, asked, sent))


class FleetCommanderRepl(SaxratRepl):
    """saxrat's own code, plus the one fold a session of broadcasts costs.

    The bindings ride in the preamble, which `imports_and_bindings` folds into
    the single `let` that asks the question, so they cost one compile rather
    than one each (#172).
    """

    BINDINGS = (
        # One reading's worth of the memory update, exactly as
        # `updateMemoryForNewReadingFromGame` assembles it.
        "broadcastReading = \\commanderMode call banner before ->"
        " fleetBroadcastMemoryAfterReading"
        " { commanderMode = commanderMode, call = call"
        " , bannerNow = banner, before = before }",
        # A session of identical readings, which is what a call nobody answers
        # looks like from in here.
        "broadcastSession = \\commanderMode call banner readings ->"
        " List.foldl (\\_ before ->"
        " broadcastReading commanderMode call banner before)"
        " initFleetBroadcastMemory (List.range 1 readings)",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-fc-repl-")
        kwargs.setdefault("preamble", tuple(PREAMBLE) + self.BINDINGS)
        super().__init__(**kwargs)


class OneRepl:
    repl = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(FleetCommanderRepl)

    @classmethod
    def tearDownClass(cls):
        if cls.repl is not None:
            cls.repl.close()


class TheClientsOwnWordsForEachVerb(OneRepl, unittest.TestCase):
    """What the client calls each verb, and which mechanism each one lives on.

    A verb defined and never sent still has to carry the right text: the whole
    point of writing the unsent ones down is that they were read off a live
    client once and should not have to be again.
    """

    def test_every_verb_carries_the_text_the_client_wrote(self):
        names = sorted(VERB_TEXT)
        self.assertEqual(
            self.repl.strings(["fleetBroadcastVerbText %s" % name
                               for name in names]),
            [VERB_TEXT[name] for name in names])

    def test_the_jump_verb_keeps_its_lowercase_to(self):
        """The one a matcher written from the English gets wrong."""
        text = self.repl.strings(
            ["fleetBroadcastVerbText BroadcastJumpTo"])[0]
        self.assertEqual(text, "Broadcast: Jump to")
        self.assertNotIn("Jump To", text)

    def test_the_eight_button_hints_are_all_present(self):
        """Every hint the fleet window draws is a verb this file can name."""
        for hint in BUTTON_HINTS:
            self.assertIn(hint, VERB_TEXT.values())

    def test_the_object_menu_verbs_are_not_looked_for_on_the_panel(self):
        answers = self.repl.evaluate([
            "fleetBroadcastVerbMechanism %s == SelectedItemMenu" % name
            for name in ("BroadcastJumpTo", "BroadcastTarget",
                         "BroadcastWarpTo", "BroadcastAlignTo",
                         "BroadcastRepairTarget")])
        self.assertEqual(answers, [True] * 5)

    def test_the_fleet_window_verbs_are_buttons(self):
        answers = self.repl.evaluate([
            "fleetBroadcastVerbMechanism %s == FleetWindowButton" % name
            for name in ("BroadcastNeedBackup", "BroadcastAtLocation",
                         "BroadcastInPositionAt", "BroadcastHoldPosition")])
        self.assertEqual(answers, [True] * 4)

    def test_exactly_four_verbs_are_sent(self):
        self.assertEqual(
            self.repl.evaluate(
                ["fleetBroadcastVerbsSent == [ %s ]" % ", ".join(VERBS_SENT)]),
            [True])

    def test_the_rest_are_defined_and_unsent(self):
        unsent = sorted(set(VERB_TEXT) - set(VERBS_SENT))
        self.assertEqual(len(unsent), 9)
        self.assertEqual(
            self.repl.evaluate(
                ["List.member %s fleetBroadcastVerbsSent" % name
                 for name in unsent]),
            [False] * len(unsent))

    def test_no_verb_moves_another_players_ship(self):
        """`Warp Fleet (Point)` is on that menu and is not a broadcast."""
        texts = self.repl.strings(
            ["fleetBroadcastVerbText %s" % name for name in sorted(VERB_TEXT)])
        for text in texts:
            self.assertNotIn("Warp Fleet", text)
        # Both strippers, since the header *documents* that these were seen and
        # left -- a case counting that prose would report the opposite of what
        # it means to.
        source = without_comments(
            without_block_comments(source_of(SAXRAT_BOT_ELM)))
        for entry in FLEET_WARP_ENTRIES:
            self.assertNotIn(entry, source)

    def test_the_header_says_the_fleet_warp_entries_were_left_alone(self):
        """Seen and declined, which an operator has to be able to read."""
        self.assertIn("Warp Fleet (Point)", source_of(SAXRAT_BOT_ELM))


class TheSettingIsTheGate(OneRepl, unittest.TestCase):
    """`fleet-commander`, which is off unless an operator says otherwise.

    The gate lives in one place -- `fleetBroadcastStep` -- so removing it is one
    mutation and it has to fail here rather than leaving three of four arms
    still gated.
    """

    def test_a_warranted_call_is_not_sent_with_the_setting_off(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == NoBroadcastToMake" % step_expression(
                    commander_mode=False)]),
            [True],
            "a call went out with `fleet-commander` unset, which is every bot "
            "in the fleet that never asked for this")

    def test_the_same_call_is_sent_with_the_setting_on(self):
        """The other half: the gate is what declines, not the warrant."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == SendTheBroadcast %s" % (
                    step_expression(commander_mode=True), call_literal())]),
            [True])

    def test_the_memory_records_nothing_with_the_setting_off(self):
        """A hundred readings of a warranted call, with the setting off."""
        self.assertEqual(
            self.repl.evaluate([
                "(broadcastSession False (Just %s) Nothing 100).sent == 0"
                % call_literal(),
                "(broadcastSession False (Just %s) Nothing 100).askedReadings"
                " == 0" % call_literal(),
                "(broadcastSession False (Just %s) Nothing 100).asking"
                " == Nothing" % call_literal()]),
            [True, True, True])

    def test_the_default_is_off(self):
        self.assertEqual(
            self.repl.evaluate([
                "defaultBotSettings.fleetCommander == AppSettings.No"]),
            [True])

    def test_the_setting_parses(self):
        self.assertEqual(
            self.repl.evaluate([
                'parseBotSettings "fleet-commander=yes"'
                " |> Result.map .fleetCommander"
                " |> (==) (Ok AppSettings.Yes)",
                'parseBotSettings "fleet-commander = no"'
                " |> Result.map .fleetCommander"
                " |> (==) (Ok AppSettings.No)"]),
            [True, True])


class TheBannerIsWhatCountsAsSent(OneRepl, unittest.TestCase):
    """De-duplication, and what a call being "sent" is allowed to mean.

    The client's broadcast banner carries the exact text of the last broadcast
    and **never clears**, which cuts both ways: it is what makes reading a call
    back possible, and it is what would make a rule keyed on "the banner
    contains our marker" confirm a call that was never sent.
    """

    AT_LOCATION = call_literal(identity="At Location in Safilbab, site AIC-1")

    def test_a_call_is_not_sent_twice(self):
        """The whole of the de-duplication, as three readings of one call.

        Reading one asks. Reading two sees the banner carrying it and latches.
        Reading three is the same warranted call again, and must produce
        nothing at all -- the banner still says it, and without the latch that
        is a broadcast on every reading for the rest of the session.
        """
        definitions = [
            "asked = broadcastReading True (Just %s) Nothing"
            " initFleetBroadcastMemory" % self.AT_LOCATION,
            'confirmed = broadcastReading True (Just %s) (Just "%s") asked'
            % (self.AT_LOCATION, LIVE_AT_LOCATION_BANNER),
            'again = broadcastReading True (Just %s) (Just "%s") confirmed'
            % (self.AT_LOCATION, LIVE_AT_LOCATION_BANNER),
        ]
        self.assertEqual(
            self.repl.evaluate([
                "asked.sent == 0",
                "confirmed.sent == 1",
                "again.sent == 1",
                "again.asking == Nothing",
                "List.length again.broadcast == 1",
            ], definitions=definitions),
            [True] * 5,
            "the same call went out twice, which is broadcast spam to real "
            "people and is what the banner is read back for")

    def test_the_step_declines_a_call_already_broadcast(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == NoBroadcastToMake" % step_expression(already=True)]),
            [True])

    def test_a_banner_unchanged_since_the_ask_confirms_nothing(self):
        """A fleet-mate's older call must not be read as this ship's own.

        The banner already said "is at location" when the ask began, because
        somebody else broadcast it. Confirming on the marker alone would latch
        a call that was never sent -- a broadcast that reports success and does
        nothing, which is this project's signature bug with the fleet as its
        subject.
        """
        definitions = [
            'asked = broadcastReading True (Just %s) (Just "%s")'
            " initFleetBroadcastMemory"
            % (self.AT_LOCATION, LIVE_AT_LOCATION_BANNER),
            'next = broadcastReading True (Just %s) (Just "%s") asked'
            % (self.AT_LOCATION, LIVE_AT_LOCATION_BANNER),
        ]
        self.assertEqual(
            self.repl.evaluate([
                "asked.sent == 0", "next.sent == 0",
                "next.asking /= Nothing"], definitions=definitions),
            [True, True, True],
            "a banner that has not changed since the ask began was read as "
            "this ship's own broadcast")

    def test_a_banner_that_names_something_else_confirms_nothing(self):
        """The marker half, on a banner that changed but is another call."""
        definitions = [
            "asked = broadcastReading True (Just %s) Nothing"
            " initFleetBroadcastMemory" % self.AT_LOCATION,
            'next = broadcastReading True (Just %s) (Just "%s") asked'
            % (self.AT_LOCATION, LIVE_BACKUP_BANNER),
        ]
        self.assertEqual(
            self.repl.evaluate(["next.sent == 0"], definitions=definitions),
            [True])

    def test_the_target_calls_own_wording_is_what_confirms_it(self):
        """`Target Centii Minion (Centii Minion)`, read back off a live client.

        Both halves are asserted, so a banner that carries the verb without the
        object -- a call about some other rat -- does not confirm this one.
        """
        call = call_literal(identity="Target '%s'" % RAT,
                            verb="BroadcastTarget",
                            must_contain=("Target", RAT))
        other = call_literal(identity="Target '%s'" % OTHER_RAT,
                             verb="BroadcastTarget",
                             must_contain=("Target", OTHER_RAT))
        self.assertEqual(
            self.repl.evaluate([
                'fleetBroadcastBannerConfirms { call = Just %s'
                ', bannerNow = Just "%s", bannerWhenAsked = Nothing }'
                % (call, LIVE_TARGET_BANNER),
                'fleetBroadcastBannerConfirms { call = Just %s'
                ', bannerNow = Just "%s", bannerWhenAsked = Nothing }'
                % (other, LIVE_TARGET_BANNER)]),
            [True, False])


class TheAskIsBounded(OneRepl, unittest.TestCase):
    """The give-up, and that the counter feeding it can actually reach it.

    #34's shape is the one to refuse here: a bound whose counter could never
    reach it. So the bound is crossed by folding the real memory update over
    real readings rather than by comparing two constants.
    """

    CALL = call_literal(identity="Jump to 'Arnon'", verb="BroadcastJumpTo",
                        must_contain=("Arnon",))

    def session(self, readings):
        return "broadcastSession True (Just %s) Nothing %d" % (
            self.CALL, readings)

    def test_the_bound_is_reached_by_a_call_nothing_answers(self):
        self.assertEqual(
            self.repl.evaluate([
                "(%s).askedReadings == %d" % (self.session(1), 0),
                "(%s).askedReadings == %d" % (
                    self.session(GIVE_UP_READINGS + 1), GIVE_UP_READINGS),
                "(%s).givenUp == 0" % self.session(GIVE_UP_READINGS + 1),
                "(%s).givenUp == 1" % self.session(GIVE_UP_READINGS + 3)]),
            [True, True, True, True],
            "the readings counter never reaches the give-up, so the bound is "
            "a comparison nothing can satisfy")

    def test_the_give_up_is_counted_once_however_long_it_lasts(self):
        """The state goes on warranting the call, so this answer repeats."""
        self.assertEqual(
            self.repl.evaluate([
                "(%s).givenUp == 1" % self.session(GIVE_UP_READINGS + 50)]),
            [True],
            "a count of readings is being reported as a count of calls")

    def test_the_step_says_give_up_past_the_bound_and_send_before_it(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == SendTheBroadcast %s" % (
                    step_expression(call=self.CALL, asked=GIVE_UP_READINGS),
                    self.CALL),
                "%s == GiveUpOnTheBroadcast \"Jump to 'Arnon'\""
                % step_expression(call=self.CALL,
                                  asked=GIVE_UP_READINGS + 1)]),
            [True, True])

    def test_a_confirmation_on_the_last_reading_still_counts(self):
        """The order of the clauses: confirm before give up.

        A call the banner reads back on the very reading the bound expires is a
        call that was sent, and recording it as abandoned would be wrong in the
        direction that sends it again.
        """
        self.assertEqual(
            self.repl.evaluate([
                "%s == RecordTheBroadcastAsSent \"Jump to 'Arnon'\""
                % step_expression(call=self.CALL, confirms=True,
                                  asking="Just \"Jump to 'Arnon'\"",
                                  asked=GIVE_UP_READINGS + 5)]),
            [True])

    def test_the_session_cap_stops_new_calls(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == NoBroadcastToMake" % step_expression(
                    call=self.CALL, sent=fleet_broadcasts_per_session()),
                "%s == SendTheBroadcast %s" % (
                    step_expression(call=self.CALL,
                                    sent=fleet_broadcasts_per_session() - 1),
                    self.CALL)]),
            [True, True])

    def test_the_give_up_reaches_the_status_line(self):
        """A `Nothing` cannot carry a decision line, so this is the only trace."""
        sentence = self.repl.strings([
            "describeFleetBroadcastGaveUp \"Jump to 'Arnon'\" 21"])[0]
        self.assertIn("Jump to 'Arnon'", sentence)
        self.assertIn("21", sentence)
        self.assertIn(str(GIVE_UP_READINGS), sentence)


def fleet_broadcasts_per_session():
    """The session cap, read out of the source it is written in."""
    body = collapsed(without_comments(
        body_of(source_of(SAXRAT_BOT_ELM), "fleetBroadcastsPerSession")))
    return int(body.rsplit(" ", 1)[-1])


class TheWarrantsAreFactsTheClientReported(OneRepl, unittest.TestCase):
    """What fires each call, asked of real parsed readings.

    The rule the issue states: fire from the signal that confirms the action, a
    jump the client reports and a lock the client reports, never from the bot's
    intention. A fleet told "in position" by a ship still aligning is being
    misled.
    """

    def identity_of(self, expression, children, definitions=()):
        return self.repl.strings(
            ["%s |> Maybe.map .identity |> Maybe.withDefault \"NONE\""
             % expression],
            definitions=list(definitions)
            + [self.repl.reading_binding("reading", children)])[0]

    def test_at_location_needs_a_lock_the_client_reports(self):
        """Rats on the overview and nothing locked is a ship on its way."""
        rows = [("18,000 m", RAT, True, False)]
        self.assertEqual(
            self.identity_of("(reading |> Maybe.andThen fleetAtLocationCall)",
                             engaged_reading(rows)),
            "NONE",
            "a ship with nothing locked told the fleet it was at location")

    def test_at_location_fires_once_the_client_shows_the_fight(self):
        rows = [("18,000 m", RAT, True, True)]
        identity = self.identity_of(
            "(reading |> Maybe.andThen fleetAtLocationCall)",
            engaged_reading(rows) + [target_in_bar(RAT, (1.0, 1.0, 1.0))])
        self.assertNotEqual(identity, "NONE")
        self.assertIn("At Location", identity)
        self.assertIn(SYSTEM, identity)

    def test_need_backup_needs_the_client_to_report_the_ship_in_warp(self):
        """Damage past the threshold, and the ship not yet going anywhere.

        Firing here would put a click in front of the warp that saves the ship,
        which is not a trade a broadcast gets to make.
        """
        rows = [("18,000 m", RAT, True, True)]
        self.assertEqual(
            self.identity_of(
                "(reading |> Maybe.andThen (fleetNeedBackupCall"
                " { incomingDamagePastTheThreshold = True }))",
                engaged_reading(rows)),
            "NONE",
            "a backup call went out on a reading the retreat still needed")

    def test_need_backup_fires_once_the_ship_is_actually_leaving(self):
        rows = [("18,000 m", RAT, True, True)]
        children = [combat_overview(rows), location_panel(SYSTEM),
                    fleet_window(BUTTON_HINTS), flying(warping=True)]
        identity = self.identity_of(
            "(reading |> Maybe.andThen (fleetNeedBackupCall"
            " { incomingDamagePastTheThreshold = True }))", children)
        self.assertIn("Need Backup", identity)

    def test_need_backup_needs_the_damage_as_well_as_the_warp(self):
        """Every warp between anomalies is a warp; only some are a retreat."""
        rows = [("18,000 m", RAT, True, True)]
        children = [combat_overview(rows), location_panel(SYSTEM),
                    fleet_window(BUTTON_HINTS), flying(warping=True)]
        self.assertEqual(
            self.identity_of(
                "(reading |> Maybe.andThen (fleetNeedBackupCall"
                " { incomingDamagePastTheThreshold = False }))", children),
            "NONE")

    def test_the_jump_call_comes_from_the_verdict_that_presses_jump(self):
        children = [plain_overview([GATE_ROW]), route_panel(ROUTE_LABELS),
                    selected_item_window(PANEL_SHOWING_THE_GATE,
                                         [JUMP_BUTTON]),
                    location_panel(SYSTEM)]
        answers = self.repl.evaluate(
            ["(reading |> Maybe.map routeStargateJumpFromReading)"
             " == Just (PressTheJumpButton \"%s\")" % NEXT_SYSTEM],
            definitions=[self.repl.reading_binding("reading", children)])
        self.assertEqual(answers, [True], "the fixture does not reach the "
                                          "verdict the jump itself decides on")
        identity = self.identity_of(
            "(reading |> Maybe.andThen fleetJumpToCall)", children)
        self.assertEqual(identity, "Jump to '%s'" % NEXT_SYSTEM)

    def test_the_jump_call_declines_where_the_panel_offers_no_jump(self):
        """The panel showing the gate is not the client offering to jump it."""
        children = [plain_overview([GATE_ROW]), route_panel(ROUTE_LABELS),
                    selected_item_window(PANEL_SHOWING_THE_GATE, []),
                    location_panel(SYSTEM)]
        self.assertEqual(
            self.identity_of("(reading |> Maybe.andThen fleetJumpToCall)",
                             children),
            "NONE")

    def test_the_jump_call_names_the_gate_it_is_about(self):
        """The confirmation, since no wording for this verb was captured."""
        children = [plain_overview([GATE_ROW]), route_panel(ROUTE_LABELS),
                    selected_item_window(PANEL_SHOWING_THE_GATE,
                                         [JUMP_BUTTON]),
                    location_panel(SYSTEM)]
        markers = self.repl.strings(
            ["(reading |> Maybe.andThen fleetJumpToCall)"
             " |> Maybe.map (.bannerMustContain >> String.join \"|\")"
             " |> Maybe.withDefault \"NONE\""],
            definitions=[self.repl.reading_binding("reading", children)])
        self.assertEqual(markers, [NEXT_SYSTEM])

    def test_the_emergency_outranks_everything_else(self):
        """A ship leaving a fight says the one thing that matters."""
        rows = [("18,000 m", RAT, True, True)]
        children = [combat_overview(rows), location_panel(SYSTEM),
                    fleet_window(BUTTON_HINTS), flying(warping=True),
                    target_in_bar(RAT, (1.0, 1.0, 1.0))]
        identity = self.identity_of(
            "(reading |> Maybe.andThen (fleetBroadcastCall"
            " { incomingDamagePastTheThreshold = True }))", children)
        self.assertIn("Need Backup", identity)


class AFleetMateIsNeverTheTarget(OneRepl, unittest.TestCase):
    """The exclusion, on the grid the capture recorded.

    The fleet's own ships were on that overview as `Imperial Navy Slicer` rows
    beside the rats. Whatever picks the row to call has to exclude fleet members
    before it clicks, the way the wingman's guard does before it locks -- and
    the row here is built to pass **every other** filter, so the pilot filter is
    the only thing that can decline it.
    """

    def called(self, rows, users):
        return self.repl.strings(
            ["reading |> Maybe.andThen ratToCallAsTarget"
             " |> Maybe.andThen .objectName |> Maybe.withDefault \"NONE\""],
            definitions=[self.repl.reading_binding(
                "reading", engaged_reading(rows, users))])[0]

    def test_a_fleet_mate_marked_as_the_active_target_is_not_called(self):
        rows = [("12,000 m", FLEET_MATE, True, True)]
        users = [chat_user_entry(FLEET_MATE, FLEET_HINT)]
        self.assertEqual(
            self.called(rows, users), "NONE",
            "a target call would have gone out on a fleet-mate's ship")

    def test_any_pilot_is_excluded_whether_or_not_the_fleet_hint_is_drawn(self):
        """Absent evidence is a pilot: a chat row with no icon still counts."""
        rows = [("12,000 m", FLEET_MATE, True, True)]
        users = [chat_user_entry(FLEET_MATE, hint=None)]
        self.assertEqual(self.called(rows, users), "NONE")

    def test_a_rat_beside_a_fleet_mate_is_still_called(self):
        """The other direction: the exclusion must not silence the feature."""
        rows = [("12,000 m", FLEET_MATE, True, False),
                ("18,000 m", RAT, True, True)]
        users = [chat_user_entry(FLEET_MATE, FLEET_HINT)]
        self.assertEqual(self.called(rows, users), RAT)

    def test_a_row_with_no_name_is_not_called(self):
        rows = [("18,000 m", "", True, True)]
        self.assertEqual(self.called(rows, []), "NONE")

    def test_the_call_is_about_the_row_the_client_marked_active(self):
        """Not a name match against rows -- #413's problem, and it applies here.

        Two rats of the same type are indistinguishable by name, so the row is
        taken from the client's own active-target marker instead.
        """
        rows = [("18,000 m", RAT, True, False),
                ("19,000 m", RAT, True, True)]
        definitions = [self.repl.reading_binding(
            "reading", engaged_reading(rows))]
        self.assertEqual(
            self.repl.evaluate([
                "reading |> Maybe.andThen ratToCallAsTarget"
                " |> Maybe.map (\\row -> overviewEntryIsActiveTarget row)"
                " |> Maybe.withDefault False"], definitions=definitions),
            [True])

    def test_nothing_is_called_where_the_client_marks_no_active_target(self):
        rows = [("18,000 m", RAT, True, False)]
        self.assertEqual(self.called(rows, []), "NONE")


class TheMechanismsAreTheOnesThatWereMeasured(OneRepl, unittest.TestCase):
    """How a call reaches the client, on fixtures shaped like the captures."""

    def test_a_button_is_found_by_its_hint_and_not_by_its_id(self):
        definitions = [self.repl.reading_binding(
            "reading", [fleet_window(BUTTON_HINTS)])]
        self.assertEqual(
            self.repl.evaluate([
                '(reading |> Maybe.andThen'
                ' (fleetWindowBroadcastButton "%s")) /= Nothing' % hint
                for hint in BUTTON_HINTS], definitions=definitions),
            [True] * len(BUTTON_HINTS))

    def test_each_button_is_a_different_node(self):
        """Six of eight share an `_elementId`, so a wrong match is invisible."""
        definitions = [self.repl.reading_binding(
            "reading", [fleet_window(BUTTON_HINTS)])]
        regions = self.repl.strings([
            '(reading |> Maybe.andThen (fleetWindowBroadcastButton "%s"))'
            " |> Maybe.map (.totalDisplayRegion >> .x >> String.fromInt)"
            ' |> Maybe.withDefault "NONE"' % hint
            for hint in BUTTON_HINTS], definitions=definitions)
        self.assertEqual(len(set(regions)), len(BUTTON_HINTS))

    def test_a_partial_hint_finds_nothing(self):
        definitions = [self.repl.reading_binding(
            "reading", [fleet_window(BUTTON_HINTS)])]
        self.assertEqual(
            self.repl.evaluate([
                '(reading |> Maybe.andThen'
                ' (fleetWindowBroadcastButton "Broadcast: Need"))'
                " == Nothing"], definitions=definitions),
            [True])

    def test_a_hint_outside_the_fleet_window_is_not_a_broadcast_button(self):
        """`fleetWindowDescendants`' scoping, which fixed a real collision."""
        stray = node("Container", {"_hint": "Broadcast: At Location"},
                     region=(0, 0, 32, 32))
        definitions = [self.repl.reading_binding("reading", [stray])]
        self.assertEqual(
            self.repl.evaluate([
                '(reading |> Maybe.andThen'
                ' (fleetWindowBroadcastButton "Broadcast: At Location"))'
                " == Nothing"], definitions=definitions),
            [True])

    def test_the_target_call_selects_the_row_before_asking_the_panel(self):
        """The panel does not re-sort and the overview does.

        Three consecutive right-clicks on moving overview rows failed in the
        capture this was written from, so the menu is opened on the Selected
        Item panel and the row is selected first.
        """
        rows = [("18,000 m", RAT, True, True)]
        call = call_literal(identity="Target '%s'" % RAT,
                            verb="BroadcastTarget",
                            must_contain=("Target", RAT))
        not_showing = self.repl.reading_binding(
            "notShowing", engaged_reading(rows))
        showing = self.repl.reading_binding(
            "showing",
            engaged_reading(rows) + [selected_item_window(RAT, [])])
        self.assertEqual(
            self.repl.evaluate([
                "(notShowing |> Maybe.andThen"
                " (fleetBroadcastRowToSelect %s)) /= Nothing" % call,
                "(showing |> Maybe.andThen"
                " (fleetBroadcastRowToSelect %s)) == Nothing" % call],
                definitions=[not_showing, showing]),
            [True, True])

    def test_the_jump_call_needs_no_selection_because_it_has_one(self):
        """`PressTheJumpButton` already means the panel is showing that gate."""
        call = call_literal(identity="Jump to '%s'" % NEXT_SYSTEM,
                            verb="BroadcastJumpTo",
                            must_contain=(NEXT_SYSTEM,))
        children = [plain_overview([GATE_ROW]), route_panel(ROUTE_LABELS),
                    selected_item_window(PANEL_SHOWING_THE_GATE,
                                         [JUMP_BUTTON])]
        self.assertEqual(
            self.repl.evaluate([
                "(reading |> Maybe.andThen (fleetBroadcastRowToSelect %s))"
                " == Nothing" % call],
                definitions=[self.repl.reading_binding("reading", children)]),
            [True])


class TheArmsAreWiredWhereTheyWereArgued(unittest.TestCase):
    """Where the sending sits in the decision tree, read off the source.

    A structural claim rather than a behavioural one, and it is the half no repl
    case can reach: an arm placed below the retreat would be counted, bounded
    and given up on without ever having been evaluated, which is a broadcast
    that reports success and does nothing.

    Read with comments stripped, so a needle cannot be satisfied by the prose
    that explains it.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def body(self, name):
        return collapsed(without_comments(body_of(self.source, name)))

    def test_the_backup_call_rides_inside_the_retreats_own_branch(self):
        root = self.body("anomalyBotDecisionRootBeforeApplyingSettings")
        self.assertIn("Maybe.map (runAwayAndTellTheFleet context)", root)

    def test_only_the_backup_call_may_preempt_the_retreat(self):
        body = self.body("runAwayAndTellTheFleet")
        self.assertIn(
            "sendFleetBroadcastAsFleetCommander [ BroadcastNeedBackup ]", body)

    def test_the_other_calls_sit_below_the_retreat(self):
        root = self.body("anomalyBotDecisionRootBeforeApplyingSettings")
        retreat = root.index("runAwayIfLowHealth context)")
        arm = root.index(
            "sendFleetBroadcastAsFleetCommander fleetBroadcastVerbsSent")
        self.assertLess(retreat, arm,
                        "the broadcast arm sits above the retreat, so a dying "
                        "ship would talk before it left")

    def test_the_memory_is_advanced_on_every_reading(self):
        """#102's placement rule: a bound counted in readings is advanced here."""
        update = self.body("updateMemoryForNewReadingFromGame")
        self.assertIn("fleetBroadcastMemoryAfterReading", update)

    def test_the_status_line_carries_the_fleet_commander_clause(self):
        status = self.body("statusTextFromState")
        self.assertIn("describeFleetCommander context", status)

    def test_the_confirmation_announces_itself_at_the_root(self):
        root = self.body("anomalyBotDecisionRoot")
        self.assertIn("context.memory.fleetBroadcast.lastChange", root)

    def test_the_call_is_built_from_exactly_the_four_warrants(self):
        """Four warrants, and no fifth arriving without passing this file.

        `fleetBroadcastVerbsSent` is the same claim written as a list; this is
        the claim about the code that actually decides, so the two cannot drift
        into disagreeing about which verbs this bot sends.
        """
        body = self.body("fleetBroadcastCall")
        warrants = sorted(set(re.findall(r"fleet\w*Call\b", body))
                          - {"fleetBroadcastCall"})
        self.assertEqual(
            warrants,
            ["fleetAtLocationCall", "fleetJumpToCall", "fleetNeedBackupCall",
             "fleetTargetCall"])


class TheOperatorCanSeeWhatIsHappening(OneRepl, unittest.TestCase):
    """The status clause, rendered rather than asserted by substring."""

    def test_off_says_so_in_the_status_line(self):
        """The answer an operator most often wants confirmed."""
        source = collapsed(without_comments(
            body_of(source_of(SAXRAT_BOT_ELM), "describeFleetCommander")))
        self.assertIn('"FC off"', source)

    def test_the_ask_says_how_far_it_has_got_and_what_confirms_it(self):
        sentence = self.repl.strings([
            "describeFleetBroadcastAsk"
            " { initFleetBroadcastMemory | askedReadings = 7 }"])[0]
        self.assertIn("7", sentence)
        self.assertIn(str(GIVE_UP_READINGS), sentence)
        self.assertIn("banner", sentence)
