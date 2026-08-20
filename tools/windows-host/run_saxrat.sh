#!/bin/bash
# Start one eve-online-saxrat run on Windows, refusing if a host is already alive.
#
#   ./run_saxrat.sh <run number> [minutes]
#   EVE_SHIP=dragoon ./run_saxrat.sh <run number> [minutes]
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

REPO="${EVE_BOT_REPO:-/c/botlab/smerwin-bots}"
LOGDIR="${EVE_BOT_LOGS:-$HOME/eve-bot-logs}"
N="$1"
MINUTES="${2:-360}"

[ -z "$N" ] && { echo "usage: run_saxrat.sh <run number> [minutes]"; exit 1; }
mkdir -p "$LOGDIR"

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
targeting-range=66000
run-away-armor-hitpoints-threshold-percent=70
run-away-incoming-damage-threshold=3500
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
# `targeting-range=40000` is the operator's figure.  Note the client stated 45
# km in its own words during run 50 and the learned `proven` bound ratcheted to
# 50 km, so this setting is the narrower of the two and is what governs.
#
# Orbit rather than keep-at-range: drones apply their damage regardless of the
# ship's own transversal, so the ship orbits to stay hard to hit.
HULL="anomaly-name=Sansha*
home-system=Amarr
targeting-range=40000
run-away-armor-hitpoints-threshold-percent=70
run-away-incoming-damage-threshold=1200
keep-at-range=no
orbit-in-combat=yes
warp-at=30
hide-when-neutral-in-local=no
accept-fleet-invite-from=Gal Bistot
follow-fleet-broadcast-from=Gal Bistot"
;;

*)
echo "unknown EVE_SHIP '$SHIP' -- known profiles: oni dragoon"
exit 1
;;
esac

SETTINGS="$SETTINGS
$HULL"

LOG="$LOGDIR/saxrat_run${N}.log"
cd "$REPO/tools/macos-host/botlab_host"
nohup python -u botlab_host.py \
    "$(cygpath -w "$REPO/implement/applications/eve-online/eve-online-saxrat")" \
    --settings "$SETTINGS" --execute-input \
    --session-duration-minutes "$MINUTES" --web-console \
    > "$LOG" 2>&1 &
echo "started run $N ($MINUTES min) -> $LOG"
