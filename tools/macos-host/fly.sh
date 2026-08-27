#!/bin/zsh
# Compile a bot and fly it, in one command, against the live client.
#
#   ./fly.sh wingman                          # compile, then fly
#   ./fly.sh saxrat --max-ticks 50            # short run
#   ./fly.sh wingman --settings-file ~/wm.txt # settings from a file
#   ./fly.sh wingman --settings "orbit-fc=no" # or inline, as the host takes it
#   ./fly.sh --help
#
# The names are the app directory's, with the `eve-online-` prefix optional:
# `wingman`, `saxrat`, `mission-runner`, `warp-to-0-autopilot`, `haulerbot`.
#
# **Why this exists.** Flying it is the fastest way to find out whether a bot
# change works, and on 2026-08-27 it was the only way: the `Fleet Member`
# cascade driven from the wrong element, the orbit flyout's mis-clicks, the
# Fleet window's rows disagreeing between pilots, and the recovery arm that
# could never rejoin were all invisible to the whole test suite and obvious
# within minutes of a live run. What made that loop slow was not compiling --
# `compile_bot.sh` is seconds -- it was the four commands around it and the
# waiting without knowing whether anything was wrong.
#
# So this does the compile first and refuses to launch if it fails, which is
# the one check that costs a second and saves a session; and it says out loud
# what the long silent parts are, because they look identical to a hang.
#
# **It logs.** `run_*.sh` do not -- `cycle_run.sh` is what tees them into
# `~/eve-bot-logs`, and a bot started any other way leaves no trace. A dev run
# is exactly the run whose log you want afterwards, so this writes one.
#
# This passes --execute-input: it WILL drive the real mouse and keyboard.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
APPS_DIR="${SCRIPT_DIR}/../../implement/applications/eve-online"
LOG_DIR="${BOT_LOG_DIR:-${HOME}/eve-bot-logs}"

for arg in "$@"; do
    case "$arg" in
        -h | --help)
            sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'
            echo ""
            echo "Apps available here:"
            for d in "$APPS_DIR"/*/Bot.elm(N); do
                echo "  ${${d:h}:t}"
            done
            exit 0
            ;;
    esac
done

if [[ $# -lt 1 ]]; then
    echo "fly.sh: which bot? Try './fly.sh --help'." >&2
    exit 2
fi

WANTED="$1"; shift

# `wingman` -> `eve-online-wingman`, but an exact directory name still wins, so
# a future app called something unfortunate cannot be shadowed by a prefix.
APP=""
for candidate in "$WANTED" "eve-online-$WANTED"; do
    if [[ -f "$APPS_DIR/$candidate/Bot.elm" ]]; then
        APP="$candidate"
        break
    fi
done
if [[ -z "$APP" ]]; then
    echo "fly.sh: no app '$WANTED' under $APPS_DIR (need a Bot.elm)." >&2
    echo "  Try './fly.sh --help' for the list." >&2
    exit 2
fi

# --settings-file is this script's own; everything else goes to the host
# untouched. Reading a file matters for a dev loop specifically: wingman needs
# a settings block to do anything at all, and retyping it every iteration is
# how you end up flying a different configuration than you meant to.
HOST_ARGS=()
SETTINGS_FILE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --settings-file)
            SETTINGS_FILE="${2-}"
            if [[ -z "$SETTINGS_FILE" ]]; then
                echo "fly.sh: --settings-file needs a path." >&2
                exit 2
            fi
            shift 2
            ;;
        *)
            HOST_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ -n "$SETTINGS_FILE" ]]; then
    if [[ ! -f "$SETTINGS_FILE" ]]; then
        echo "fly.sh: no settings file at $SETTINGS_FILE" >&2
        exit 2
    fi
    HOST_ARGS+=(--settings "$(cat "$SETTINGS_FILE")")
fi

echo "fly.sh: $APP"

# 1. Compile first. A type error found here costs a second; found after the
#    guard below it costs whatever was flying.
echo "  compiling..."
if ! "${SCRIPT_DIR}/compile_bot.sh" "$APP"; then
    echo "fly.sh: $APP does not compile -- not launching." >&2
    exit 1
fi

# 2. The native tools, same reason run_saxrat.sh does it: they are gitignored
#    build output that nothing else refreshes.
"${SCRIPT_DIR}/build_tools.sh" >/dev/null || {
    echo "fly.sh: a native tool failed to build -- refusing to start." >&2
    exit 1
}

# 3. Guard: one bot at a time on this machine. Named rather than silent: on a
#    machine that is also flying the fleet, "what did I just stop" is not a
#    question to answer by guessing.
BOT_PATTERNS='run_mission\.sh|run_saxrat\.sh|run_autopilot\.sh|fly\.sh|botlab_host\.py|driver\.js|tree_walker/tree_walker'
self_pid=$$
running=()
for pid in $(pgrep -f "$BOT_PATTERNS" 2>/dev/null); do
    [[ "$pid" == "$self_pid" ]] && continue
    running+=("$pid")
done
if (( ${#running} > 0 )); then
    echo "  stopping ${#running} process(es) from a previous run: ${running[*]}"
    for pid in "${running[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 1
fi

mkdir -p "$LOG_DIR"
SHORT="${APP#eve-online-}"
n=1
for f in "$LOG_DIR"/${SHORT}_dev*.log(N); do
    seq="${${f:t:r}#${SHORT}_dev}"
    [[ "$seq" == <-> ]] && (( seq >= n )) && n=$(( seq + 1 ))
done
LOG="$LOG_DIR/${SHORT}_dev${n}.log"

cat <<'NOTE'

  What to expect, so the quiet parts do not read as a hang:
    - "Setting up volatile process" and "Search the address of the UI root"
      can run for MINUTES with no error and no visible progress. A saxrat
      start on this Mac was measured recreating the volatile process 41 times
      over ~5 minutes before its first decision. That is slow, not stuck.
    - The first line beginning with "+" is the first real decision. That is
      the moment the bot is actually flying.
  Ctrl-C to stop.

NOTE
echo "  logging to $LOG"
echo ""

# `script -q` keeps the host's stdout line-buffered through the pipe, so the
# log and the terminal both stay live; a plain pipe blocks it into chunks and
# the startup phases above arrive minutes late, in a lump, which defeats the
# point of printing them.
exec script -q /dev/null python3 "${SCRIPT_DIR}/botlab_host/botlab_host.py" \
    "$APPS_DIR/$APP" --web-console --execute-input "${HOST_ARGS[@]}" \
    2>&1 | tee "$LOG"
