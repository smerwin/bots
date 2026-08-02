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
# A session of this script's own, not a general-purpose one. `screen -X stuff`
# goes to whichever window the session has selected, and this default used to be
# "saxrat" -- a session that had since become the one hosting an interactive
# Claude Code terminal. Stuffing there types the launcher command into that
# prompt instead of a shell, and --stop sends it Ctrl-C. Neither reports an
# error: screen accepts the command and the bot simply never starts.
SCREEN_SESSION="${BOT_SCREEN:-evebot}"
# Absolute, not "./run_mission.sh": the command is stuffed into a screen session
# whose working directory this script does not control, and which does drift --
# a cycle failed with "no such file or directory: ./run_mission.sh" after the
# session had been cd'd elsewhere, leaving no bot running at all.
LAUNCHER="${BOT_LAUNCHER:-${SCRIPT_DIR}/run_mission.sh}"
# Logs outlive the session that started the run: run numbering is continuous
# across runs (CLAUDE.md cites run 111, 114, 129 by number), and comparing a
# stall against earlier runs is the main way a pathology gets recognised. This
# default used to be a per-session scratchpad under /private/tmp, which is
# removed when that session goes away -- taking every previous run's log with
# it, and leaving `tee` writing into a directory that no longer exists.
LOG_DIR="${BOT_LOG_DIR:-${HOME}/eve-bot-logs}"
LOG_PREFIX="${BOT_LOG_PREFIX:-mission_run}"

# tee fails silently into a missing directory: the bot still starts, nothing is
# logged, and start() then waits five minutes for decisions it will never see.
mkdir -p "$LOG_DIR"

# Everything a bot run spawns. run_mission.sh's own guard uses the same set.
BOT_PATTERNS='run_mission\.sh|run_saxrat\.sh|botlab_host\.py|driver\.js|tree_walker/tree_walker|cg_input/cg_input'

bot_pids() { pgrep -f "$BOT_PATTERNS" 2>/dev/null | grep -v "^$$\$" || true; }

screen_session_pid() {
    screen -ls 2>/dev/null \
        | awk -v name="$SCREEN_SESSION" '$1 ~ "^[0-9]+\\." name "$" { split($1, a, "."); print a[1]; exit }'
}

# `screen -X stuff` goes to whichever window the session has selected, running
# whatever it happens to be running. When that session is an ancestor of this
# process, the target is the terminal we are executing in: the launcher command
# gets typed into that prompt and stop()'s Ctrl-C interrupts it. screen reports
# success either way, so the only symptom is a bot that never starts.
refuse_if_target_is_our_own_terminal() {
    local target; target="$(screen_session_pid)"
    [[ -z "$target" ]] && return 0
    local p="$$"
    while [[ -n "$p" && "$p" != 0 && "$p" != 1 ]]; do
        if [[ "$p" == "$target" ]]; then
            print -u2 "refusing: screen session '${SCREEN_SESSION}' (pid ${target}) hosts this very process."
            print -u2 "  Stuffing it would type into our own terminal. Set BOT_SCREEN to another session."
            return 1
        fi
        p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"
    done
    return 0
}

# A freshly created session's shell is not ready the moment `screen -dmS`
# returns: login and the profile take a beat, and anything stuffed before the
# shell reads stdin is dropped without a word. That is how a cycle reported
# "starting -> mission_run1.log" while nothing ran and no log was ever created.
# Wait for a probe command to genuinely execute instead of guessing a sleep.
session_accepts_input() {
    local probe="${TMPDIR:-/tmp}/cycle_run_probe.$$"
    rm -f "$probe"
    for _ in {1..20}; do
        screen -S "$SCREEN_SESSION" -X stuff ": > ${probe}$(printf '\r')" 2>/dev/null || true
        sleep 0.5
        [[ -f "$probe" ]] && { rm -f "$probe"; return 0; }
    done
    return 1
}

ensure_session() {
    [[ -n "$(screen_session_pid)" ]] && return 0
    print "creating screen session '${SCREEN_SESSION}'"
    screen -dmS "$SCREEN_SESSION"
    [[ -n "$(screen_session_pid)" ]] || return 1
    session_accepts_input
}

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

    refuse_if_target_is_our_own_terminal || return 1

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
    refuse_if_target_is_our_own_terminal || return 1
    ensure_session || { print -u2 "could not create screen session '${SCREEN_SESSION}'"; return 1; }
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
