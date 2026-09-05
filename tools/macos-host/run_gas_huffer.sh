#!/bin/zsh
# Launches the eve-online-gas-huffer bot (implement/applications/eve-online/
# eve-online-gas-huffer) via botlab_host.py.
#
# NOTICES BUT CANNOT LEAVE. Since #461 that app warps to a gas site, picks the
# cloud whose designation carries the highest trailing number, orbits it, keeps
# the propulsion module running, locks it and runs both harvesters; since #462
# it also refreshes the Directional Scanner and says on every reading whether
# anything on the grid means leave. It does **not** retreat (#463), deposit the
# hold when it fills (#464), or keep the propulsion module on across a warp
# (#465). So a run left unattended in a wormhole is a ship that will still be
# sitting on its cloud when somebody else warps in -- knowing they are there and
# doing nothing about it. It says so on every reading rather than looking busy,
# which is the whole reason it is launchable at all.
#
# Before running, per this bot's own setup instructions (see its Bot.elm
# header): set the UI language to English; open the overview, the probe scanner
# with its Group column visible, the Directional Scanner and Local chat; leave
# the scan bound to `V`, which is the client's own default; and -- the one that
# cannot be checked from inside the bot -- orbit something by hand once at the
# range you want, because the Selected Item panel's Orbit button orbits at
# whatever range the client last used.
#
# Like run_autopilot.sh and unlike run_saxrat.sh / run_mission.sh, this passes
# **no default settings at all**. Every setting this bot has either names
# something particular to one operator's wormhole, corporation or bookmarks, or
# already has a sensible default in the source, so the useful launcher default
# is none. Pass --settings yourself.
#
# Run `./run_gas_huffer.sh --help` for this bot's settings and the host's flags.
# Any extra arguments are passed straight through to botlab_host.py.
#
# This always passes --execute-input -- it WILL click and type for real.
# Don't use your computer for anything else while it's running.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
BOT_SOURCE="${SCRIPT_DIR}/../../implement/applications/eve-online/eve-online-gas-huffer"

USAGE='./run_gas_huffer.sh                                     # no settings, every default in the source
./run_gas_huffer.sh --settings "home-structure-name=Example Refinery"
./run_gas_huffer.sh --settings "friendly-ship-tag=[EXMPL]"     # unset means every ship reads hostile
./run_gas_huffer.sh --max-ticks 50                             # short run, then stop
./run_gas_huffer.sh --help                                     # this text'

# Answered before the guard below: asking what the flags are must not kill a
# session that is already running.
for arg in "$@"; do
    case "$arg" in
        -h | --help)
            python3 "${SCRIPT_DIR}/bot_help.py" "$BOT_SOURCE" \
                --script "run_gas_huffer.sh" \
                --summary "runs the eve-online-gas-huffer bot, which is meant to harvest gas from a wormhole site and leave the moment anything else turns up. Since #462 it does the harvesting and the watching, and NONE of the leaving: it reports what is on the grid on every reading and does not retreat (#463), deposit the hold (#464) or keep the propulsion module on across a warp (#465)." \
                --note "This always passes --execute-input: it WILL drive your real mouse and
keyboard. Starting a run also kills any bot session already running, since two
of them fighting over the cursor produces chaos.

This launcher passes NO default settings. Anything naming a structure, a fleet
tag or a bookmark convention is yours to write, and nothing identifying is
committed to this repository.

One setup item cannot be checked from inside the bot: orbit something by hand
once, at the range you want, before starting. The Selected Item panel's Orbit
button orbits at whatever range the client last used, and there is no way to
command a distance." \
                --usage "$USAGE"
            exit 0
            ;;
    esac
done

# Rebuild any native tool whose source has moved since it was last compiled.
# Before the guard below, so a build failure leaves a running bot alone instead
# of killing it and then refusing to start.
"${SCRIPT_DIR}/build_tools.sh" || {
    echo "run_gas_huffer.sh: a native tool failed to build -- refusing to start." >&2
    echo "  The old binary is still in place, and running it is what this check exists to stop." >&2
    exit 1
}

# Preflight: can this application actually read window titles? Screen Recording
# is granted per application, and without it every window's title comes back as
# `(null)`, so `find_eve_processes` finds nothing and the run ends with "I did
# not find an EVE Online client process" -- which names the one thing that was
# definitely not wrong. See run_autopilot.sh for the observed case.
if [[ -x "${SCRIPT_DIR}/window_probe/window_probe" ]]; then
    titled=$("${SCRIPT_DIR}/window_probe/window_probe" --all 2>/dev/null \
        | grep -v 'name=(null)' \
        | grep -cv 'owner="Window Server"\|owner="Dock"' || true)
    if [[ "$titled" -eq 0 ]]; then
        echo "run_gas_huffer.sh: this application cannot read window titles, so the host" >&2
        echo "  will report 'I did not find an EVE Online client process' no matter what is running." >&2
        echo "" >&2
        echo "  Grant Screen Recording to whichever terminal you are running this from:" >&2
        echo "    System Settings -> Privacy & Security -> Screen Recording" >&2
        echo "  then quit and reopen that terminal -- the grant is not picked up until it restarts." >&2
        exit 1
    fi
fi

# Guard: one bot at a time. A stale run left alive from a previous session would
# still be clicking and typing against the game client and fighting this one for
# control, so kill any previous launcher wrapper (matched by basename, since it
# may have been invoked with a relative or absolute path) and the host processes
# it spawned. `pgrep -f` also matches this very script's own just-started
# process, so its own pid is excluded rather than killing ourselves before we
# get going. Note `pgrep -f` without `-l` matches the command line without
# printing it, which is what keeps the client's credentials out of this output.
self_pid=$$
for pattern in "run_gas_huffer\.sh" "run_autopilot\.sh" "run_mission\.sh" "run_saxrat\.sh" "botlab_host/botlab_host.py" "botlab_host/driver.js" "tree_walker/tree_walker"; do
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do
        [[ "$pid" == "$self_pid" ]] && continue
        kill "$pid" 2>/dev/null || true
    done
done
sleep 1

# No --settings here on purpose: see the header. An explicit --settings later on
# the command line still reaches the host, since "$@" is appended.
python3 "${SCRIPT_DIR}/botlab_host/botlab_host.py" "$BOT_SOURCE" \
    --web-console \
    --execute-input "$@"
