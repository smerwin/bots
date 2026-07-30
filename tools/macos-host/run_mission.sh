#!/bin/zsh
# Launches the eve-online-mission-runner combat mission bot
# (implement/applications/eve-online/eve-online-mission-runner) via
# botlab_host.py.
#
# The bot takes a security mission from an agent in station, flies out to the
# site, clears each pocket, follows the acceleration gates between them,
# returns, and turns the mission in. It navigates using the mission tracker's
# own travel button in the info panel rather than setting routes itself.
#
# Before running, per this bot's own setup instructions (see its Bot.elm
# header): set the UI language to English; open the overview and drones
# windows; sort the overview by distance (nearest at top); make sure the
# overview shows acceleration gates, or the bot cannot follow a mission from
# one pocket to the next; filter empty wrecks out of the overview, so that
# looting cargo out of destroyed ships terminates instead of reopening wrecks
# it has already emptied; in the ship UI, put combat modules in the top row,
# the propulsion module first in the middle row, and hide passive modules;
# keep the default drone keybinds (Shift+F launch, F engage, Shift+R recall);
# bind the 'W' key to orbit.
#
# Start it docked in the station where the agent is. It will pick up whatever
# mission is already running, or ask the agent for a new one.
#
# Usage:
#   ./run_mission.sh                       # runs with --execute-input: takes over your real mouse/keyboard
#   ./run_mission.sh --max-ticks 50
#   ./run_mission.sh --settings "agent-name=Some Agent"   # overrides the defaults below
#   ./run_mission.sh --session-duration-minutes 180        # default is 60
#   SESSION_DURATION_MINUTES=180 ./run_mission.sh          # same, via the environment
# Any extra arguments are passed straight through to botlab_host.py.
#
# This always passes --execute-input -- it WILL click and type for real.
# Don't use your computer for anything else while it's running.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
BOT_SOURCE="${SCRIPT_DIR}/../../implement/applications/eve-online/eve-online-mission-runner"

# Guard: one bot at a time. A stale run left alive from a previous session
# would still be clicking/typing against the game client and fighting this
# one for control, so kill any previous bot wrapper (matched by basename,
# since it may have been invoked with a relative or absolute path) and the
# host processes it spawned, before starting a new one. run_saxrat.sh is in
# the list too -- the two bots drive the same mouse and must never overlap.
# (pgrep -f also matches this very script's own just-started process, so its
# own pid is excluded rather than killing ourselves before we get going.)
self_pid=$$
for pattern in "run_mission\.sh" "run_saxrat\.sh" "botlab_host/botlab_host.py" "botlab_host/driver.js" "tree_walker/tree_walker"; do
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do
        [[ "$pid" == "$self_pid" ]] && continue
        kill "$pid" 2>/dev/null || true
    done
done
sleep 1

# Default settings. All of these are optional -- the bot runs with none of
# them -- but these are a reasonable starting point.
#
# agent-name is left unset on purpose: with no name configured the bot uses
# the first agent the station lists under "Available to you", which is the
# right choice in a station with a single usable agent. Set it explicitly if
# the station has several.
#
# keep-at-range suits a ship that fights at range with turrets; switch to
# orbit-in-combat=yes for a ship that wants to stay close instead. Only one
# of the two should be 'yes'.
#
# targeting-range is the max distance (meters) to lock a target from the
# overview; beyond it the bot approaches instead of locking.
#
# The run-away thresholds dock the ship up when it drops below them. Shield
# is disabled (-1) because shields recharge and dipping into them is normal
# in a mission; armor damage is not, so 80% is a real warning sign.
#
# No attack-object entries are needed for the ordinary case: when a mission
# objective names a structure to kill ("You need to destroy the <a ...>Drone
# Silo</a>"), the bot reads the name straight out of the objective. The setting
# remains available as an override for anything that does not cover.
#
# Either way the object must be enabled in the overview's type filters
# (Overview Settings -> Types -> Celestial -> Large Collidable Object), or the
# bot never sees it in the first place.
#
# decline-mission skips a mission by name. The bot uses the agent's "Delay"
# button rather than "Decline", since declining more than once every four hours
# costs standing. Matched case-insensitively as a substring, so "Worlds Collide"
# also covers the higher-level variants of the same mission.
#
# Worlds Collide: its acceleration gates restrict entry to smaller hulls than
# the cruiser this is flown in, so the site cannot be completed at all -- not a
# difficulty judgement, a hard gate restriction.
# approach-object covers missions that ask you to get close to something but
# name the wrong thing: "Athran Exigency" says to approach an Acidic Cloud,
# which is decoration and is not even on the overview, while the Abandoned
# Mining Station on the same grid is what actually satisfies it. Tried after
# whatever the objective itself names.
#
# prefer-wreck searches particular hulls first when a mission wants cargo out of
# destroyed ships. Purely an optimisation -- every other wreck is still opened
# afterwards, so a wrong guess costs only a wasted trip.
SETTINGS="orbit-in-combat=no
keep-at-range=yes
targeting-range=66000
decline-mission=Worlds Collide
prefer-wreck=Personnel Transport
approach-object=Abandoned Mining Station
run-away-shield-hitpoints-threshold-percent=-1
run-away-armor-hitpoints-threshold-percent=80"

# How long this session should run. The bot stops taking new work and docks
# once ~200 seconds remain, so it finishes parked in a station rather than
# being cut off mid-warp with drones out. Override by passing the flag again
# on the command line.
SESSION_DURATION_MINUTES="${SESSION_DURATION_MINUTES:-60}"

# An explicit --settings or --session-duration-minutes later on the command
# line wins: botlab_host.py's argument parser takes the last occurrence, so
# appending "$@" after ours is what makes the overrides in the usage examples
# above work.
python3 "${SCRIPT_DIR}/botlab_host/botlab_host.py" "$BOT_SOURCE" \
    --settings "$SETTINGS" \
    --session-duration-minutes "$SESSION_DURATION_MINUTES" \
    --execute-input "$@"
