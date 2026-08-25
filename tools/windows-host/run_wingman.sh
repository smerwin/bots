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
# WINGMAN.md is explicit that nothing here has flown yet, and that it carries
# no health-based retreat guard at all -- unlike every saxrat hull profile,
# `defaultBotSettings` has no `run-away-*` field and `Bot.elm` has no retreat
# logic beyond a shield-percent status line. That is why MINUTES defaults
# short here (40) rather than to saxrat's 360: this is a first flight, meant
# to be watched, not an unattended six-hour session.
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
