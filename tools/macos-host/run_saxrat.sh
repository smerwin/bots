#!/bin/zsh
# Launches the eve-online-saxrat combat anomaly bot (implement/applications/
# eve-online/eve-online-saxrat) via botlab_host.py, with the settings
# example from that bot's own Bot.elm doc comment as sensible defaults.
#
# This bot's own EveOnline/* and Common/* framework files predated the
# ones eve-online-mining-bot has been updated to (it was still on the
# older BotLab host interface, retired with wingus -- see
# notes/retire-wingus.md). Migrated it to the current framework files and
# adapted Bot.elm's few call sites that used
# now-changed framework APIs (context-menu-cascade custom choices,
# mouseClickOnUIElement's Result return type, the merged
# ifSeeShipUI/ifUndockingComplete branch). Confirmed working end-to-end in
# dry-run mode against the live game before enabling real input here: it
# compiles, finds the UI root, reads real game state, and computes a real
# context-menu click.
#
# Before running, per this bot's own setup instructions (see its Bot.elm
# header): set the UI language to English; undock; open the probe
# scanner, overview, and drones windows; sort the overview by distance
# (nearest at top); in the ship UI, put combat modules in the top row and
# hide passive modules; bind the 'W' key to orbit.
#
# Run `./run_saxrat.sh --help` for the usage examples, this bot's settings and
# the host's flags -- it prints the USAGE and SETTINGS defined below plus
# botlab_host.py's own flag list, so there is no second copy here to drift.
# Any extra arguments are passed straight through to botlab_host.py.
#
# This always passes --execute-input -- it WILL click and type for real.
# Don't use your computer for anything else while it's running.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
BOT_SOURCE="${SCRIPT_DIR}/../../implement/applications/eve-online/eve-online-saxrat"

USAGE='./run_saxrat.sh                                # start a run
./run_saxrat.sh --max-ticks 50                 # short run, then stop
./run_saxrat.sh --settings "anomaly-name=..."  # replaces the defaults below wholesale
./run_saxrat.sh --help                         # this text'

# Default settings string: the exact example from eve-online-saxrat's own
# Bot.elm doc comment, i.e. the bot author's own suggested starting point,
# not something invented here. Adjust freely -- these are reasonable
# defaults, not the only correct choice.
#
# warp-at is the distance (km) used when warping to an anomaly -- it must
# match one of the game client's own preset "Warp to Within" distances
# (typically 0, 5, 10, 15, 20, 30, 50, 70, 100), not an arbitrary number,
# or the bot will get stuck unable to find a matching menu entry.
#
# targeting-range is the max distance (meters) to lock a target from the
# overview; beyond it the bot approaches instead of locking.
#
# fleet-commander is off here on purpose, and it is listed rather than omitted.
# --settings replaces this whole block wholesale, so a launch of
# `--settings "fleet-commander=yes"` would start a saxrat with no anomaly-name,
# no warp-at and no thresholds -- a bot that broadcasts and cannot hunt. Having
# the line here means turning the feature on is editing a `no` to a `yes`
# rather than retyping fourteen settings correctly from memory.
#
# With it on the bot sends fleet broadcasts as well as reading them; see the
# `fleet-commander` entry in eve-online-saxrat's own Bot.elm header for which
# four, and what each one fires from.
SETTINGS="anomaly-name=sansha hideaway
anomaly-name=sansha refuge
anomaly-name=sansha burrow
anomaly-name=sansha forsaken hideaway
anomaly-name=sansha hidden hideaway
anomaly-name=sansha forlorn hideaway
hide-when-neutral-in-local = no
orbit-in-combat=yes
keep-at-range=no
warp-at=10
targeting-range=37000
run-away-shield-hitpoints-threshold-percent=-1
run-away-armor-hitpoints-threshold-percent=80
fleet-commander=no"

# Answered before the guard below: asking what the flags are must not kill a
# session that is already running.
for arg in "$@"; do
    case "$arg" in
        -h | --help)
            python3 "${SCRIPT_DIR}/bot_help.py" "$BOT_SOURCE" \
                --script "run_saxrat.sh" \
                --summary "runs the eve-online-saxrat combat anomaly bot, which hunts combat anomalies from the probe scanner and kills rats with drones and weapon modules." \
                --note "This always passes --execute-input: it WILL drive your real mouse and
keyboard. Starting a run also kills any bot session already running, since two
of them fighting over the cursor produces chaos. Set the game client up first
-- see the instructions at the top of this script." \
                --usage "$USAGE" \
                --defaults "$SETTINGS"
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
    echo "run_saxrat.sh: a native tool failed to build -- refusing to start." >&2
    echo "  The old binary is still in place, and running it is what this check exists to stop." >&2
    exit 1
}

# Guard: one bot at a time. A stale run left alive from a previous session
# would still be clicking/typing against the game client and fighting this
# one for control, so kill any previous run_saxrat.sh wrapper (matched by
# basename, since it may have been invoked with a relative or absolute
# path) and the host processes it spawned, before starting a new one.
# (pgrep -f also matches this very script's own just-started process, so
# its own pid is excluded rather than killing ourselves before we get
# going.)
self_pid=$$
for pattern in "run_saxrat\.sh" "botlab_host/botlab_host.py" "botlab_host/driver.js" "tree_walker/tree_walker"; do
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do
        [[ "$pid" == "$self_pid" ]] && continue
        kill "$pid" 2>/dev/null || true
    done
done
sleep 1

python3 "${SCRIPT_DIR}/botlab_host/botlab_host.py" "$BOT_SOURCE" --settings "$SETTINGS" --execute-input "$@"
