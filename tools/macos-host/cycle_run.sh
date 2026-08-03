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

# Output that means the run is over and no decision is ever coming.
#
# `^Traceback` is every way botlab_host.py gives up: an `elm make` type error
# (the common one -- compile_bot raises RuntimeError("elm make failed") and
# main() has no handler), a missing Bot.elm, an unsupported host interface.
# Match the traceback header and not the exception line, because Python colours
# the exception even when stderr is a pipe -- through `tee` the last line reads
# `\e[1;35mRuntimeError\e[0m: \e[35melm make failed\e[0m`, so the obvious
# `grep 'RuntimeError: elm make failed'` finds nothing. The header is plain.
#
# `^-- SOMETHING ----` is elm's own error report, printed just above that
# traceback and unescaped. It is redundant as a trigger but names the culprit
# where the traceback only names botlab_host.py.
#
# `^zsh:` is the launcher never running at all -- a stale absolute path in
# BOT_LAUNCHER, or python3 missing. Nothing else the run prints starts that way.
#
# Checked against a full 4.4 MB log of a healthy run: zero matches. The bot's
# own status text does wrap onto unprefixed lines, and some of them are rules of
# dashes, which is why the elm pattern requires a capitalised word after the two.
FATAL_LOG_PATTERNS='^Traceback \(most recent call last\):|^-- [A-Z][A-Z ]+-+|^zsh:'

# How many consecutive polls of an unchanging log, with nothing matching
# BOT_PATTERNS alive, it takes to call a run dead. The process check is what
# carries this -- run_mission.sh is itself in BOT_PATTERNS and lives for the
# whole session, so a compiling run is never mistaken for a dead one -- and the
# log check only has to cover the moment between the last process exiting and
# its final output reaching the file.
DEAD_STABLE_POLLS=2

# 100 polls of 3s is the five minutes start() will wait. Overridable so the
# tests can drive the same loop in under a second.
WAIT_POLL_SECONDS="${BOT_WAIT_POLL_SECONDS:-3}"
WAIT_POLL_COUNT="${BOT_WAIT_POLL_COUNT:-100}"
LOG_TAIL_LINES="${BOT_LOG_TAIL_LINES:-15}"

log_size() { [[ -f "$1" ]] && wc -c < "$1" | tr -d ' ' || print 0; }

# Every way of failing to start ends with the operator opening the log, so put
# its tail in the failure message instead of pointing at it. On stderr with the
# message it belongs to, so a caller keeping only stdout still sees the whole
# diagnosis together.
print_log_tail() {
    if [[ -s "$1" ]]; then
        tail -n "$LOG_TAIL_LINES" "$1" | sed 's/^/  | /' >&2
    else
        print -u2 "  | ${1:t} is empty or was never created -- nothing the launcher ran wrote a byte"
    fi
}

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
        # (Nom) is next_log()'s idiom: empty on no match, newest first. The
        # `ls -t` this replaces aborted the whole script under `set -e` with
        # "no matches found" whenever the log directory was still empty, so
        # --status reported correctly and then exited 1.
        local newest=( "$LOG_DIR"/${LOG_PREFIX}*.log(Nom) )
        if (( ${#newest} )); then
            print "log: ${newest[1]:t} ($(wc -l < "${newest[1]}" | tr -d ' ') lines)"
        fi
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

# A run that dies during compilation never writes a decision, so wait on the
# log rather than on the process, and give up rather than hang forever.
#
# That reasoning is right and stays. What it could not do was tell "not yet"
# from "never": a type error in Bot.elm is diagnosed in seconds by reading the
# log, and this used to sit on it for the full five minutes before saying only
# "check the screen session". So each poll now also asks whether the run is
# provably over, two ways.
#
# The second way needs both halves. No process alone is wrong -- `screen -X
# stuff` returns before the session's shell has even read the line, so there is
# a window where nothing is running because nothing has started yet. A static
# log alone is wrong too, since elm can spend a while between lines. Requiring a
# non-empty log closes the first window from the other side: `tee` creates the
# file, and the launcher writes to it long before it could plausibly have died.
#
# Split out from start() so the tests can drive it against a fake log and a
# stubbed bot_pids() -- see tests/test_cycle_run.py.
wait_for_first_decision() {
    local log="$1"
    local size last_size=-1 stable=0
    for _ in {1..$WAIT_POLL_COUNT}; do
        if [[ -s "$log" ]] && grep -q 'Middle-row modules\|Combat feed\|^+ ' "$log" 2>/dev/null; then
            print "  live: $(bot_pids | tr '\n' ' ')"
            grep -E '^\+ ' "$log" | tail -1 | sed 's/^/  /'
            return 0
        fi
        if [[ -s "$log" ]] && grep -qE "$FATAL_LOG_PATTERNS" "$log" 2>/dev/null; then
            print -u2 "  the run failed before its first decision:"
            print_log_tail "$log"
            return 1
        fi
        size="$(log_size "$log")"
        if [[ -s "$log" && "$size" == "$last_size" && -z "$(bot_pids | tr -d ' \n')" ]]; then
            stable=$(( stable + 1 ))
            if (( stable >= DEAD_STABLE_POLLS )); then
                print -u2 "  the run is gone: nothing matching BOT_PATTERNS is alive and the log stopped growing:"
                print_log_tail "$log"
                return 1
            fi
        else
            stable=0
        fi
        last_size="$size"
        sleep "$WAIT_POLL_SECONDS"
    done
    print -u2 "  no decisions after $(( WAIT_POLL_COUNT * WAIT_POLL_SECONDS ))s -- check the screen session"
    print_log_tail "$log"
    return 1
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
    wait_for_first_decision "$log"
}

# Sourced (`toplevel:file`) rather than executed (`toplevel`) means a test
# wants the functions, not a cycle. Without this, sourcing with no arguments
# defaults to "cycle" and stops the running bot.
if [[ "$ZSH_EVAL_CONTEXT" == toplevel ]]; then
    case "${1:-cycle}" in
        --status) status ;;
        --stop)   stop ;;
        cycle)    stop && start ;;
        *)        print -u2 "usage: $0 [--stop|--status]"; exit 2 ;;
    esac
fi
