#!/bin/zsh
# Launches the eve-online-warp-to-0-autopilot bot (implement/applications/
# eve-online/eve-online-warp-to-0-autopilot) via botlab_host.py. It follows
# the route already set in the in-game autopilot, warping directly to gates
# and stations rather than to the 15 km the game's own autopilot leaves you
# at.
#
# Before running, per this bot's own setup instructions (see its Bot.elm
# header): set the UI language to English; set the in-game autopilot route;
# expand the autopilot info panel so the route is visible; and leave the
# overview visible, so the stargate the route names can be identified. The
# bot still travels without the overview, on the context menu alone -- it is
# the faster Jump-button path that needs it.
#
# Unlike run_saxrat.sh and run_mission.sh, this passes no default settings:
# every setting this bot has is optional (`activate-module-always` is the
# only one), so the useful default is none at all. Pass --settings yourself
# to set one.
#
# Run `./run_autopilot.sh --help` for this bot's settings and the host's
# flags. Any extra arguments are passed straight through to botlab_host.py.
#
# This always passes --execute-input -- it WILL click and type for real.
# Don't use your computer for anything else while it's running.
#
# For the Spotlight-launchable wrapper around this script, see
# install_autopilot_app.sh in this directory.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
BOT_SOURCE="${SCRIPT_DIR}/../../implement/applications/eve-online/eve-online-warp-to-0-autopilot"

USAGE='./run_autopilot.sh                                       # travel the route now set in game
./run_autopilot.sh --max-ticks 50                        # short run, then stop
./run_autopilot.sh --settings "activate-module-always=cloaking device"
./run_autopilot.sh --help                                # this text'

# Answered before the guard below: asking what the flags are must not kill a
# session that is already running.
for arg in "$@"; do
    case "$arg" in
        -h | --help)
            python3 "${SCRIPT_DIR}/bot_help.py" "$BOT_SOURCE" \
                --script "run_autopilot.sh" \
                --summary "runs the eve-online-warp-to-0-autopilot bot, which follows the route set in the in-game autopilot and warps directly to each gate and station instead of to 15 km short of it." \
                --note "This always passes --execute-input: it WILL drive your real mouse and
keyboard. Starting a run also kills any bot session already running, since two
of them fighting over the cursor produces chaos. Set the route in the game
client first -- see the instructions at the top of this script." \
                --usage "$USAGE"
            exit 0
            ;;
    esac
done

# Rebuild any native tool whose source has moved since it was last compiled.
# The Elm bot is recompiled on every run; the C tools are gitignored build
# output that nothing refreshed, so a pulled fix to one of them could sit
# unbuilt indefinitely -- see build_tools.sh for the day that cost every typed
# character. Before the guard below, so a build failure leaves the running bot
# alone instead of killing it and then refusing to start.
"${SCRIPT_DIR}/build_tools.sh" || {
    echo "run_autopilot.sh: a native tool failed to build -- refusing to start." >&2
    echo "  The old binary is still in place, and running it is what this check exists to stop." >&2
    exit 1
}

# Preflight: can this application actually read window titles?
#
# Screen Recording is granted per application, and without it every window's
# title comes back as `(null)`. The host's WINDOW_LINE_RE expects `name="..."`
# and does not match that, so `_windows_for` finds nothing, `find_eve_processes`
# returns nothing, and the run ends with "I did not find an EVE Online client
# process" -- which names the one thing that was definitely not wrong. Observed
# 2026-08-25: Terminal.app had no grant and failed exactly this way while
# iTerm2 ran the same script fine.
#
# System-owned windows (the menubar, the Dock's wallpaper) carry titles
# regardless of the grant, so "some window somewhere has a title" is not the
# test. Whether any *other* application's window does is.
if [[ -x "${SCRIPT_DIR}/window_probe/window_probe" ]]; then
    titled=$("${SCRIPT_DIR}/window_probe/window_probe" --all 2>/dev/null \
        | grep -v 'name=(null)' \
        | grep -cv 'owner="Window Server"\|owner="Dock"' || true)
    if [[ "$titled" -eq 0 ]]; then
        echo "run_autopilot.sh: this application cannot read window titles, so the host" >&2
        echo "  will report 'I did not find an EVE Online client process' no matter what is running." >&2
        echo "" >&2
        echo "  Grant Screen Recording to whichever terminal you are running this from:" >&2
        echo "    System Settings -> Privacy & Security -> Screen Recording" >&2
        echo "  then quit and reopen that terminal -- the grant is not picked up until it restarts." >&2
        exit 1
    fi
fi

# Guard: one bot at a time. A stale run left alive from a previous session
# would still be clicking/typing against the game client and fighting this one
# for control, so kill any previous launcher wrapper (matched by basename,
# since it may have been invoked with a relative or absolute path) and the
# host processes it spawned, before starting a new one. (pgrep -f also matches
# this very script's own just-started process, so its own pid is excluded
# rather than killing ourselves before we get going.)
self_pid=$$
for pattern in "run_autopilot\.sh" "run_mission\.sh" "run_saxrat\.sh" "botlab_host/botlab_host.py" "botlab_host/driver.js" "tree_walker/tree_walker"; do
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do
        [[ "$pid" == "$self_pid" ]] && continue
        kill "$pid" 2>/dev/null || true
    done
done
sleep 1

# No --settings here on purpose: see the header. An explicit --settings later
# on the command line still reaches the host, since "$@" is appended.
python3 "${SCRIPT_DIR}/botlab_host/botlab_host.py" "$BOT_SOURCE" \
    --web-console \
    --execute-input "$@"
