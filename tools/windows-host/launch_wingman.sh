#!/bin/bash
# Start one eve-online-wingman run on Windows with an operator-chosen FC and
# retreat thresholds, refusing if a host is already alive.
#
#   ./launch_wingman.sh [run number] [minutes]
#
# Every knob is an env var, because unlike run_saxrat.sh's ship profiles there
# is no small fixed set of wingman configurations worth naming -- the FC and
# the thresholds change from session to session and the operator states them
# fresh each time:
#
#   EVE_WINGMAN_FC                    default: Gal Bistot
#   EVE_WINGMAN_APPROACH_FC           default: yes   (set empty to omit the line
#                                                      entirely and take Bot.elm's
#                                                      own default)
#   EVE_WINGMAN_SHIELD_THRESHOLD      default: -1    (run-away-shield-hitpoints-threshold-percent)
#   EVE_WINGMAN_ARMOR_THRESHOLD       default: -1    (run-away-armor-hitpoints-threshold-percent)
#   EVE_WINGMAN_DAMAGE_THRESHOLD      default: -1    (run-away-incoming-damage-threshold)
#
# All three retreat thresholds default to -1 (off), matching run_wingman.sh's
# own stated caution: these are facts about a hull under fire, not something
# to guess. Pass real numbers once a run has supplied them.
#
#   EVE_WINGMAN_FC="Gal Bistot" \
#   EVE_WINGMAN_SHIELD_THRESHOLD=-1 \
#   EVE_WINGMAN_ARMOR_THRESHOLD=90 \
#   EVE_WINGMAN_DAMAGE_THRESHOLD=800 \
#   ./launch_wingman.sh 16 360
#
# This is run_wingman.sh's own header, unchanged, for every trap that script
# already documents (the one-bot guard, why the settings block is a here-doc,
# why the tree is checked before the run starts, why the settings get written
# to the log before host stderr) -- read that file first if this is unfamiliar
# territory. What is different here is only that the settings are assembled
# from the environment instead of being fixed in the script.
set -e

REPO="${EVE_BOT_REPO:-/c/botlab/bots}"
LOGDIR="${EVE_BOT_LOGS:-$HOME/eve-bot-logs}"
mkdir -p "$LOGDIR"

N="$1"
if [ -z "$N" ]; then
    LAST=$(ls "$LOGDIR"/wingman_run*.log 2>/dev/null \
        | sed -E 's/.*wingman_run([0-9]+)\.log/\1/' | sort -n | tail -1)
    N=$(( ${LAST:-0} + 1 ))
fi
MINUTES="${2:-40}"

FC="${EVE_WINGMAN_FC:-Gal Bistot}"
APPROACH_FC="${EVE_WINGMAN_APPROACH_FC-yes}"
SHIELD_THRESHOLD="${EVE_WINGMAN_SHIELD_THRESHOLD:--1}"
ARMOR_THRESHOLD="${EVE_WINGMAN_ARMOR_THRESHOLD:--1}"
DAMAGE_THRESHOLD="${EVE_WINGMAN_DAMAGE_THRESHOLD:--1}"

powershell -NoProfile -ExecutionPolicy Bypass \
    -File "$(cygpath -w "$REPO/tools/windows-host/stop_bots.ps1")" | tr -d '\r'

echo "--- working tree ---"
cd "$REPO"
git log --oneline -1
BOT="implement/applications/eve-online/eve-online-wingman/Bot.elm"
[ -f "$BOT" ] || { echo "  $BOT not found -- wrong tree, refusing to start"; exit 1; }
for f in fleetPilotNames broadcastVerbsNotYetRead textAfterBroadcastTimestamp; do
    c=$(grep -c "$f" "$BOT")
    printf "  %-28s %s\n" "$f" "$c"
    [ "$c" = "0" ] && { echo "  MISSING -- wrong tree, refusing to start"; exit 1; }
done

# accept-fleet-invite-from is where the trust in this bot sits -- see
# WINGMAN.md's own words: "Accepting means the fleet can warp this ship and
# call its targets."
SETTINGS="accept-fleet-invite-from=$FC
follow-fleet-broadcast-from=$FC"

if [ -n "$APPROACH_FC" ]; then
    SETTINGS="$SETTINGS
approach-fc=$APPROACH_FC"
fi

SETTINGS="$SETTINGS
run-away-shield-hitpoints-threshold-percent=$SHIELD_THRESHOLD
run-away-armor-hitpoints-threshold-percent=$ARMOR_THRESHOLD
run-away-incoming-damage-threshold=$DAMAGE_THRESHOLD"

LOG="$LOGDIR/wingman_run${N}.log"
cd "$REPO/tools/macos-host/botlab_host"

echo "--- settings ---" > "$LOG"
echo "$SETTINGS" >> "$LOG"
echo "---" >> "$LOG"

nohup python -u botlab_host.py \
    "$(cygpath -w "$REPO/implement/applications/eve-online/eve-online-wingman")" \
    --settings "$SETTINGS" --execute-input \
    --session-duration-minutes "$MINUTES" --web-console \
    >> "$LOG" 2>&1 &
disown
echo "started run $N ($MINUTES min, FC $FC) -> $LOG"
