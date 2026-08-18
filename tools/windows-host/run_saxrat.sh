#!/bin/bash
# Start one eve-online-saxrat run on Windows, refusing if a host is already alive.
#
#   ./run_saxrat.sh <run number> [minutes]
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
#
# The armour percentage guard stays at 70 and is hull-agnostic -- it is what
# carried run 35 through 85 retreats without a loss.  The shield one stays off:
# on an armour-tanked hull the shield is a fuse rather than a buffer and rests
# near 0%, so a shield threshold trips a minute into every fight and never
# releases.  With both unset, CLAUDE.md's `ATTRITION UNGUARDED` clause fires and
# nothing is watching the hull at all.
#
# `hide-when-neutral-in-local=no` is the one whose absence silently parks the
# bot: with it defaulted the other way, a neutral in local means it tethers and
# does nothing for the rest of the session while every log line looks healthy.
SETTINGS="$SETTINGS
anomaly-name=Sansha*
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

LOG="$LOGDIR/saxrat_run${N}.log"
cd "$REPO/tools/macos-host/botlab_host"
nohup python -u botlab_host.py \
    "$(cygpath -w "$REPO/implement/applications/eve-online/eve-online-saxrat")" \
    --settings "$SETTINGS" --execute-input \
    --session-duration-minutes "$MINUTES" --web-console \
    > "$LOG" 2>&1 &
echo "started run $N ($MINUTES min) -> $LOG"
