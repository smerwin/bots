#!/bin/zsh
# Launches the eve-online-saxrat combat anomaly bot (implement/applications/
# eve-online/eve-online-saxrat) via botlab_host.py, with the settings
# example from that bot's own Bot.elm doc comment as sensible defaults.
#
# This bot's own EveOnline/* and Common/* framework files predated the
# ones eve-online-mining-bot has been updated to (it was still on the
# BotLab.BotInterface_To_Host_2023_02_06 interface). Migrated it to the
# current framework files and adapted Bot.elm's few call sites that used
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
# Usage:
#   ./run_saxrat.sh              # runs with --execute-input: takes over your real mouse/keyboard
#   ./run_saxrat.sh --max-ticks 50
# Any extra arguments are passed straight through to botlab_host.py.
#
# This always passes --execute-input -- it WILL click and type for real.
# Don't use your computer for anything else while it's running.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
BOT_SOURCE="${SCRIPT_DIR}/../../implement/applications/eve-online/eve-online-saxrat"

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
SETTINGS="anomaly-name=sansha hideaway
anomaly-name=sansha refuge
anomaly-name=sansha burrow
anomaly-name=sansha forsaken hideaway
anomaly-name=sansha hidden hideaway
anomaly-name=sansha forlorn hideaway
hide-when-neutral-in-local = no
orbit-in-combat=no
keep-at-range=yes
warp-at=50
targeting-range=66000
run-away-shield-hitpoints-threshold-percent=-1
run-away-armor-hitpoints-threshold-percent=80"

python3 "${SCRIPT_DIR}/botlab_host/botlab_host.py" "$BOT_SOURCE" --settings "$SETTINGS" --execute-input "$@"
