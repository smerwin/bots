#!/bin/bash
# Start one eve-online-saxrat run on Windows, refusing if a host is already alive.
#
#   ./run_saxrat.sh [run number] [minutes]
#   EVE_SHIP=dragoon ./run_saxrat.sh [run number] [minutes]
#   EVE_SHIP=slicer  ./run_saxrat.sh [run number] [minutes]
#
# [run number] is optional and auto-increments from the highest
# saxrat_run<N>.log already in LOGDIR -- WINDOWS.md used to tell an operator to
# `ls -t ~/eve-bot-logs | grep -E 'saxrat_run[0-9]+\.log'` by hand and take one
# past the highest, because reusing a number truncates that run's log. This is
# that lookup, done for you; passing a number explicitly still works exactly as
# before, unchanged.
#
# The macOS launcher next door (tools/macos-host/run_saxrat.sh) is the model.
# What is different here is entirely the platform, and all of it is a trap that
# has already cost this project a session:
#
#   * **The refusal is the point.**  `pkill -f botlab_host.py` does not work on
#     Windows -- Git Bash cannot see native processes or their command lines, so
#     it matches nothing, exits non-zero and reads exactly like a clean stop.
#     One session accumulated *seven* hosts that way, one per "restart", all
#     driving the same mouse, which CLAUDE.md calls chaos.  `stop_bots.ps1` uses
#     `Win32_Process` and proves the stop rather than assuming it; this script
#     refuses to start if it reports any host left.
#
#   * **The settings block is a here-doc'd string sent to the bot verbatim.**
#     Every comment about it must stay OUTSIDE the quoted string.  An
#     unrecognised key is not ignored: `AppSettings` answers `Unknown setting
#     name` and `BotFramework` ends the session at startup.
#
#   * **The tree is checked before the run starts.**  A settings string naming a
#     rule the checked-out `Bot.elm` does not have compiles and flies as though
#     it were configured.  The three identifiers below are the cheapest proof
#     that this is the tree the settings were written for.
#
# Logs go to ~/eve-bot-logs, the same place every other run in this project
# writes to, because that directory *is* the corpus every measurement in
# CLAUDE.md is recounted from.  Earlier Windows runs went to a session scratch
# directory instead, which put them outside it -- override with EVE_BOT_LOGS.
set -e

REPO="${EVE_BOT_REPO:-/c/botlab/bots}"
LOGDIR="${EVE_BOT_LOGS:-$HOME/eve-bot-logs}"
mkdir -p "$LOGDIR"

N="$1"
if [ -z "$N" ]; then
    LAST=$(ls "$LOGDIR"/saxrat_run*.log 2>/dev/null \
        | sed -E 's/.*saxrat_run([0-9]+)\.log/\1/' | sort -n | tail -1)
    N=$(( ${LAST:-0} + 1 ))
fi
MINUTES="${2:-360}"

powershell -NoProfile -ExecutionPolicy Bypass \
    -File "$(cygpath -w "$REPO/tools/windows-host/stop_bots.ps1")" | tr -d '\r'

echo "--- working tree ---"
cd "$REPO"
git log --oneline -1
BOT="implement/applications/eve-online/eve-online-saxrat/Bot.elm"
for f in anomalyNameMatches strayContextMenuGiveUpTicks followFleetBroadcastFrom; do
    c=$(grep -c "$f" "$BOT")
    printf "  %-32s %s\n" "$f" "$c"
    [ "$c" = "0" ] && { echo "  MISSING -- wrong tree, refusing to start"; exit 1; }
done

# The hunting circuit.  One `hunt-system=` line per system; the bot walks them
# in order and asks the host to set each destination through ESI.
SETTINGS=$(printf 'hunt-system=%s\n' \
    Hamse Lashkai Zhilshinou Ana Jaswelu Shumam Nalu Hiramu \
    Knophtikoo Fora Safilbab Kerepa Nosodnis Sizamod Seitam)

# `hide-when-neutral-in-local=no` is the one whose absence silently parks the
# bot: with it defaulted the other way, a neutral in local means it tethers and
# does nothing for the rest of the session while every log line looks healthy.
#
# The armour percentage guard stays at 70 in both profiles and is hull-agnostic
# -- it is what carried run 35 through 85 retreats without a loss.  The shield
# one stays off: on an armour-tanked hull the shield is a fuse rather than a
# buffer and rests near 0%, so a shield threshold trips a minute into every
# fight and never releases.
#
# The hull-specific half.  `EVE_SHIP` picks it; the circuit above is shared.
#
# This is a profile rather than an edit-in-place because the settings for a run
# have twice now survived only in a session transcript: the log echoes the
# source path, the commit and every learned bound, and *not one line of the
# settings string it was started with*.  Run 50 flew a Dragoon for six hours and
# the only record of what it was configured with is what a reader can infer back
# out of the status clauses (`lock 40000m`, `dmg N/1200`, `attrition guarded
# (shield -1 armor 70)`, `Ammo swap: off`).  That is recoverable and it is not a
# record.
SHIP="${EVE_SHIP:-oni}"

case "$SHIP" in
oni)
# Omen Navy Issue.  The ship is 'Bene', read off the client, and its crystals
# are Medium -- `Multifrequency M` verbatim from the cargo row, which is what
# makes the size suffix a reading rather than a guess.  Both charge names must
# match the weapon's own right-click menu exactly or the swap looks configured
# and never fires.
#
# `run-away-incoming-damage-threshold` is 3500, the repo's own calibrated
# figure, measured on a larger hull.  2000 was a judgement for the Coercer Navy
# Issue and would be twitchy on a cruiser with several times the buffer.  Still
# a judgement: #119's live hull-scaling is in the mission runner and has never
# been ported here, so nothing derives this.
HULL="anomaly-name=Sansha*
short-range-ammo=Multifrequency M
long-range-ammo=Radio M
ammo-swap-range=20000
home-system=Amarr
targeting-range=39000
run-away-armor-hitpoints-threshold-percent=70
run-away-incoming-damage-threshold=1200
keep-at-range=yes
orbit-in-combat=no
warp-at=30
hide-when-neutral-in-local=no
accept-fleet-invite-from=Gal Bistot
follow-fleet-broadcast-from=Gal Bistot"
;;

dragoon)
# Dragoon, a drone destroyer.  Flown for run 50: 214 kills over 17 anomalies
# with no retreat and the ship at 100% armour when the client died.
#
# **No ammo settings at all**, and their absence is the configuration rather
# than an omission -- a Dragoon fights with drones and has no turret to load, so
# naming a charge would arm a swap that can never find a weapon menu to read.
# The bot says so on every reading (`Ammo swap: off (needs ...)`), which is the
# state to expect here and not a fault.
#
# `run-away-incoming-damage-threshold` is 1200 rather than 3500, and it is the
# one number here derived from evidence rather than carried over: the Coercer
# lost on 2026-08-18 died having taken **3,522** damage against a 3500
# threshold, so the guard was 99.4% of that hull's durability and could only
# fire at the moment of death.  A destroyer needs a threshold well inside its
# own buffer.  Run 50 never tripped it across repeated `Tower Sentry Sansha I`
# fights -- the same rat class that killed the Coercer -- peaking at 925, which
# is the evidence that 1200 is placed rather than merely lower.
#
# `targeting-range=36000` is the operator's figure, tightened from the 40000
# run 50 flew under.  The client stated 45 km in its own words during run 50
# and the learned `proven` bound ratcheted to 50 km, so this setting is still
# the narrowest of the three and is what governs -- nothing here re-derives it
# from evidence, it is a deliberate tightening for this run.
#
# Orbit rather than keep-at-range: drones apply their damage regardless of the
# ship's own transversal, so the ship orbits to stay hard to hit.
HULL="anomaly-name=Sansha*
home-system=Amarr
targeting-range=36000
run-away-armor-hitpoints-threshold-percent=70
run-away-incoming-damage-threshold=1200
keep-at-range=no
orbit-in-combat=yes
warp-at=30
hide-when-neutral-in-local=no
accept-fleet-invite-from=Gal Bistot
follow-fleet-broadcast-from=Gal Bistot"
;;

coercer)
# Coercer Navy Issue 'Pew Pew Pew', flown by Cathy Crokite. Real lock range
# read off the client is 37.4 km; targeting-range is set narrower than that
# deliberately, same posture as the dragoon profile.
#
# `run-away-incoming-damage-threshold=2500` and
# `run-away-armor-hitpoints-threshold-percent=80` are this hull's own numbers
# from the 2026-08-19/20 handoff, not carried over from oni or dragoon -- the
# previous ship on this account (an Omen Navy Issue) was lost to a Sansha
# escalation on 17 Aug, at 100%->5% armour in under two minutes, while its
# client-side "Keep at Range" default sat at 7,500 m instead of a distance
# matched to the fit. That default is a per-client setting, not a bot one --
# see PILOT.md's "Intervening by hand" -- and must be checked on this hull
# before a run, not assumed from the settings string below.
#
# short-range-ammo/long-range-ammo name the crystals as the weapon's own
# right-click menu writes them for this hull (Multifrequency S / Aurora S).
# The cargo has carried only Aurora S at times; the swap then correctly
# reports "carries neither charge" and keeps firing Aurora rather than
# latching disarmed -- that is expected, not a fault.
HULL="anomaly-name=Sansha*
short-range-ammo=Multifrequency S
long-range-ammo=Aurora S
ammo-swap-range=20000
home-system=Amarr
targeting-range=35000
run-away-armor-hitpoints-threshold-percent=80
run-away-incoming-damage-threshold=2500
keep-at-range=yes
orbit-in-combat=no
warp-at=30
hide-when-neutral-in-local=no
accept-fleet-invite-from=Gal Bistot
follow-fleet-broadcast-from=Gal Bistot"
;;

slicer)
# Slicer, Kara Kernite's sniper frigate. First run under this profile -- there
# is no combat history yet to derive `run-away-incoming-damage-threshold` from,
# unlike oni and dragoon. 1200 is the operator's own figure for this hull's
# buffer, not something measured here; watch the first run's `dmg N/1200` and
# tighten or loosen it once real damage windows exist.
#
# **No ammo settings at all**, deliberately, same shape as dragoon and for a
# different reason: this is a fixed long-range fit on Aurora crystals only, so
# there is no second charge to swap to. Naming one charge with none to swap
# between would arm a swap that can never complete. Aurora is loaded by hand
# before the run; the bot never touches ammo here.
#
# Orbit rather than keep-at-range, matching the sniper doctrine: at
# targeting-range=56000 the ship holds range on the orbit itself rather than
# needing a separate keep-at-range command.
HULL="anomaly-name=Sansha*
home-system=Amarr
targeting-range=56000
run-away-armor-hitpoints-threshold-percent=70
run-away-incoming-damage-threshold=1200
keep-at-range=no
orbit-in-combat=yes
warp-at=30
hide-when-neutral-in-local=no
accept-fleet-invite-from=Olivia Ochre
follow-fleet-broadcast-from=Olivia Ochre"
;;

tristan)
# Tristan, a T1 frigate -- the first profile here for a hull this small, on
# Heather Hemorphite's currently-open client (inferred from which client was
# active when this profile was written, not independently confirmed against
# a character-select screen).
#
# **No ammo settings, and it may not even be an omission**: a Tristan is
# commonly fit as a pure droneboat (light drones, no turret at all), the
# same shape the dragoon profile documents its own absence of ammo settings
# for. If this fit does carry a turret, the swap simply stays unconfigured
# rather than guessing a charge name this profile has no evidence for --
# the bot reports `Ammo swap: off` either way, which is expected here and
# not a fault.
#
# `run-away-incoming-damage-threshold=500` is an **unverified guess, not a
# measurement** -- the only figures this file has (1200 for a destroyer,
# 2500 for a Navy Issue destroyer) were both calibrated on hulls with far
# more total EHP than a T1 frigate, and reusing either here would very
# plausibly be well past what a Tristan can absorb in one 45-second window,
# which is exactly the failure #32 exists to prevent -- a guard that can
# only fire at the moment of death is not a guard. 500 was chosen to be
# clearly on the cautious side (more false retreats, which cost nothing but
# a trip home, rather than a threshold discovered too late) rather than
# derived from anything this hull has actually done. Two runs have flown
# under it since (148: 6h at 360 min; 149: 90 min) and both ended at
# `dmg 0/500` with the retreat never firing -- consistent with the guess
# being on the cautious side, but neither run stressed it, so 500 is still
# unverified rather than confirmed. **Watch `dmg N/500` and this hull's own
# peak window on a run that actually takes damage** the way the Coercer's
# 2500 was derived from its own recorded peaks, and correct this number once
# there is a real peak to replace the guess with.
#
# `run-away-armor-hitpoints-threshold-percent=70` is kept at the same value
# every other profile here uses -- the script's own comment above calls it
# hull-agnostic, calibrated on what carried run 35 through 85 retreats with
# no loss, and nothing about a smaller hull changes that argument.
#
# `targeting-range=46000` and `orbit-in-combat=yes` (with `keep-at-range=no`
# to match, since the two are opposites in every profile here) are the
# operator's own figures for this run, not derived from anything measured.
HULL="anomaly-name=Sansha*
home-system=Amarr
targeting-range=46000
run-away-armor-hitpoints-threshold-percent=70
run-away-incoming-damage-threshold=500
keep-at-range=no
orbit-in-combat=yes
warp-at=30
hide-when-neutral-in-local=no
accept-fleet-invite-from=Gal Bistot
follow-fleet-broadcast-from=Gal Bistot"
;;

*)
echo "unknown EVE_SHIP '$SHIP' -- known profiles: oni dragoon coercer slicer tristan"
exit 1
;;
esac

SETTINGS="$SETTINGS
$HULL"

LOG="$LOGDIR/saxrat_run${N}.log"
cd "$REPO/tools/macos-host/botlab_host"

# No log line has ever named the settings string a run was started with --
# WINDOWS.md's own section on it says a handoff note is the only record and
# calls that "recoverable and ... not a record". This is that record, written
# to the log itself before the host's own stderr starts, so it survives
# alongside the run rather than in whichever terminal happened to be open.
echo "--- settings (profile: $SHIP) ---" > "$LOG"
echo "$SETTINGS" >> "$LOG"
echo "---" >> "$LOG"

nohup python -u botlab_host.py \
    "$(cygpath -w "$REPO/implement/applications/eve-online/eve-online-saxrat")" \
    --settings "$SETTINGS" --execute-input \
    --session-duration-minutes "$MINUTES" --web-console \
    >> "$LOG" 2>&1 &
echo "started run $N ($MINUTES min) -> $LOG"
