#!/bin/bash
# Start one eve-online-wingman run on Windows, refusing if a host is already
# alive.
#
#   ./run_wingman.sh [run number] [minutes]
#
# Modelled on run_saxrat.sh in this same directory -- read that file's own
# header first if this is unfamiliar territory, since every trap it documents
# (the one-bot guard, why the settings block is a here-doc, why the tree is
# checked before the run starts, why the settings get written to the log)
# applies here unchanged.
#
# [run number] is optional and auto-increments from the highest
# wingman_run<N>.log already in LOGDIR, same as run_saxrat.sh's own lookup.
#
# `Bot.elm` has carried a health retreat since #364 -- `retreatToTheCommander`,
# with the same two instruments saxrat uses -- but **it is not armed here and
# no `run-away-*` line is written into the settings block below**. Those
# thresholds are facts about a hull and no wingman run has recorded what this
# one does under fire, so they default to -1 and stay there until a fought run
# supplies the numbers WINGMAN.md's "Not verified" lists. Until then this ship
# still flies with nothing watching its health, which is why MINUTES defaults
# short here (40) rather than to saxrat's 360: a session meant to be watched,
# not an unattended six-hour tour.
#
# `--session-duration-minutes` is required for a different reason too:
# WINGMAN.md says the trip home only fires once `secondsToSessionEnd` is set,
# so omitting it means the bot never routes home when the session ends.
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
# call its targets." Gal Bistot is the fleet commander every saxrat profile in
# the sibling launcher already names.
SETTINGS="accept-fleet-invite-from=Gal Bistot
follow-fleet-broadcast-from=Gal Bistot"

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
echo "started run $N ($MINUTES min) -> $LOG"
