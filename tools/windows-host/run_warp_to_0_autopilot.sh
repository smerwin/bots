#!/bin/bash
# Start one eve-online-warp-to-0-autopilot run on Windows, refusing if a host
# is already alive.
#
#   ./run_warp_to_0_autopilot.sh [run number] [minutes]
#
# Same guard as run_saxrat.sh next door, and for the identical reason: Git
# Bash cannot see native Windows processes or their command lines, so a
# `pkill` looks like a stop and is not one -- see run_saxrat.sh's own header.
# stop_bots.ps1 proves the stop rather than assuming it, and it matches by
# process name and command line, so it stops this bot exactly as it stops
# saxrat; only one host may drive the mouse at a time.
#
# This bot has almost no settings -- see its own Bot.elm header -- so there is
# no hull profile to pick, unlike run_saxrat.sh. It follows whatever route the
# client's own in-game autopilot already has set, with the autopilot info
# panel and the overview both visible. Set the route and open both panels
# before starting this, not after.
#
# [run number] is optional and auto-increments from the highest
# warp_to_0_run<N>.log already in LOGDIR, so a bare
# `./run_warp_to_0_autopilot.sh` just works. [minutes] is also optional; when
# omitted the session runs with no automatic time limit, which matches how
# this bot is actually used -- kicked off before a manual travel stretch and
# stopped by hand (or by the next stop_bots.ps1) once it lands.
set -e

REPO="${EVE_BOT_REPO:-/c/botlab/bots}"
LOGDIR="${EVE_BOT_LOGS:-$HOME/eve-bot-logs}"
mkdir -p "$LOGDIR"

N="$1"
if [ -z "$N" ]; then
    LAST=$(ls "$LOGDIR"/warp_to_0_run*.log 2>/dev/null \
        | sed -E 's/.*warp_to_0_run([0-9]+)\.log/\1/' | sort -n | tail -1)
    N=$(( ${LAST:-0} + 1 ))
fi
MINUTES="$2"

powershell -NoProfile -ExecutionPolicy Bypass \
    -File "$(cygpath -w "$REPO/tools/windows-host/stop_bots.ps1")" | tr -d '\r'

echo "--- working tree ---"
cd "$REPO"
git log --oneline -1
BOT="implement/applications/eve-online/eve-online-warp-to-0-autopilot/Bot.elm"
c=$(grep -c "activateModulesAlways" "$BOT")
printf "  %-32s %s\n" "activateModulesAlways" "$c"
[ "$c" = "0" ] && { echo "  MISSING -- wrong tree, refusing to start"; exit 1; }

# `activate-module-always` is the one setting this bot has (e.g. a cloaking
# device). Set EVE_ACTIVATE_MODULE to name one; leave it unset for none.
SETTINGS="${EVE_ACTIVATE_MODULE:+activate-module-always=$EVE_ACTIVATE_MODULE}"

LOG="$LOGDIR/warp_to_0_run${N}.log"
cd "$REPO/tools/macos-host/botlab_host"

DURATION_ARGS=()
[ -n "$MINUTES" ] && DURATION_ARGS=(--session-duration-minutes "$MINUTES")

# Same reasoning as run_saxrat.sh's settings echo: nothing else records what a
# run was actually started with, so it goes in the log itself, before the
# host's own stderr starts.
echo "--- settings ---" > "$LOG"
echo "$SETTINGS" >> "$LOG"
echo "---" >> "$LOG"

nohup python -u botlab_host.py \
    "$(cygpath -w "$REPO/implement/applications/eve-online/eve-online-warp-to-0-autopilot")" \
    --settings "$SETTINGS" --execute-input \
    "${DURATION_ARGS[@]}" --web-console \
    >> "$LOG" 2>&1 &
echo "started warp-to-0 run $N -> $LOG"
