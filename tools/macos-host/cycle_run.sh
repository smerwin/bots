#!/bin/zsh
# Stop the running bot and start a fresh one in the screen session, logging to
# the next run number.
#
#   ./cycle_run.sh            # stop, then start the next run
#   ./cycle_run.sh --stop     # stop only
#   ./cycle_run.sh --status   # what is running and where it is logging
#
# Stopping is the part that needs care. Ctrl-C into the screen session is the
# polite way and usually works, but it goes to whatever has the foreground there
# -- and when that is not the bot, the keystroke lands somewhere harmless and the
# bot keeps running. That happened, silently, and the "stopped" report was wrong
# until the processes were checked directly. So this escalates: Ctrl-C, then
# TERM, then KILL, verifying between each, and it will not start a new run until
# the old one is genuinely gone. Two bots sharing a mouse is chaos worth
# preventing.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
SCREEN_SESSION="${BOT_SCREEN:-saxrat}"
# Absolute, not "./run_mission.sh": the command is stuffed into a screen session
# whose working directory this script does not control, and which does drift --
# a cycle failed with "no such file or directory: ./run_mission.sh" after the
# session had been cd'd elsewhere, leaving no bot running at all.
LAUNCHER="${BOT_LAUNCHER:-${SCRIPT_DIR}/run_mission.sh}"
LOG_DIR="${BOT_LOG_DIR:-/private/tmp/claude-501/-Users-smerwin-code-bots/8486a8c5-32d8-4523-ac86-9f9c3a68aaec/scratchpad}"
LOG_PREFIX="${BOT_LOG_PREFIX:-mission_run}"

# Everything a bot run spawns. run_mission.sh's own guard uses the same set.
BOT_PATTERNS='run_mission\.sh|run_saxrat\.sh|botlab_host\.py|driver\.js|tree_walker/tree_walker|cg_input/cg_input'

bot_pids() { pgrep -f "$BOT_PATTERNS" 2>/dev/null | grep -v "^$$\$" || true; }

status() {
    local pids; pids="$(bot_pids | tr '\n' ' ')"
    if [[ -z "${pids// }" ]]; then
        print "not running"
    else
        print "running: $pids"
        local newest; newest="$(ls -t "$LOG_DIR"/${LOG_PREFIX}*.log 2>/dev/null | head -1)"
        [[ -n "$newest" ]] && print "log: ${newest:t} ($(wc -l < "$newest" | tr -d ' ') lines)"
    fi
}

stop() {
    [[ -z "$(bot_pids | tr -d ' \n')" ]] && { print "nothing to stop"; return 0; }

    print "stopping..."
    screen -S "$SCREEN_SESSION" -X stuff $'\003' 2>/dev/null || true
    for _ in {1..10}; do
        [[ -z "$(bot_pids | tr -d ' \n')" ]] && { print "  stopped (Ctrl-C)"; return 0; }
        sleep 1
    done

    # Ctrl-C did not reach it -- see the note at the top.
    print "  Ctrl-C did not take, sending TERM"
    local pids; pids="$(bot_pids | tr '\n' ' ')"
    [[ -n "${pids// }" ]] && kill ${=pids} 2>/dev/null || true
    for _ in {1..5}; do
        [[ -z "$(bot_pids | tr -d ' \n')" ]] && { print "  stopped (TERM)"; return 0; }
        sleep 1
    done

    print "  still up, sending KILL"
    pids="$(bot_pids | tr '\n' ' ')"
    [[ -n "${pids// }" ]] && kill -9 ${=pids} 2>/dev/null || true
    sleep 2
    if [[ -n "$(bot_pids | tr -d ' \n')" ]]; then
        print -u2 "  FAILED to stop: $(bot_pids | tr '\n' ' ')"
        return 1
    fi
    print "  stopped (KILL)"
}

next_log() {
    local highest=0
    for f in "$LOG_DIR"/${LOG_PREFIX}*.log(N); do
        local n="${${f:t:r}#$LOG_PREFIX}"
        [[ "$n" == <-> ]] && (( n > highest )) && highest=$n
    done
    print "${LOG_DIR}/${LOG_PREFIX}$(( highest + 1 )).log"
}

start() {
    if [[ -n "$(bot_pids | tr -d ' \n')" ]]; then
        print -u2 "refusing to start: a bot is still running"
        return 1
    fi
    local log; log="$(next_log)"
    print "starting -> ${log:t}"
    screen -S "$SCREEN_SESSION" -X stuff "${LAUNCHER} 2>&1 | tee ${log}$(printf '\r')"

    # A run that dies during compilation never writes a decision, so wait on the
    # log rather than on the process, and give up rather than hang forever.
    for _ in {1..100}; do
        [[ -s "$log" ]] && grep -q 'Middle-row modules\|Combat feed\|^+ ' "$log" 2>/dev/null && {
            print "  live: $(bot_pids | tr '\n' ' ')"
            grep -E '^\+ ' "$log" | tail -1 | sed 's/^/  /'
            return 0
        }
        sleep 3
    done
    print -u2 "  no decisions after 5 minutes -- check the screen session"
    return 1
}

case "${1:-cycle}" in
    --status) status ;;
    --stop)   stop ;;
    cycle)    stop && start ;;
    *)        print -u2 "usage: $0 [--stop|--status]"; exit 2 ;;
esac
