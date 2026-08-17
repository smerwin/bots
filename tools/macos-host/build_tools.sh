#!/bin/zsh
# Rebuild any native tool whose source has changed since its binary was built.
#
# The six C tools are gitignored build output, so nothing about pulling a change
# to one of them updates what actually runs. Before this script there was also
# nothing that *noticed*: the launchers recompile the Elm bot on every run --
# `botlab_host.py` copies the bot directory and runs `elm make` every time --
# while the C half of the same executable surface was last built whenever
# somebody last remembered to. MACOS.md says "Redo this only if you edit the
# .c files", which is a manual step and was missed.
#
# What that cost, on 2026-08-16: `cg_input` on this machine was compiled Aug 2
# and its source was Aug 14, so PR #241 -- "cg_input posts the key's own flags
# and its own modifiers, not the session's" -- had never run here. Every key the
# bot posted carried the session's stray `SecondaryFn`, which the bot's own
# F1-F4 weapon hotkeys assert, so the client received Globe chords instead of
# text and every typed string arrived empty. Mouse clicks were unaffected, since
# a stray Fn on a click is harmless -- so the symptom was "clicks work, typing
# does nothing", which reads like a focus bug and is not one.
#
# That is this repo's signature failure with the toolchain as its subject: every
# layer reported success, the log showed the effects dispatched, and the
# characters were being corrupted below all of it.
#
# Staleness is judged over every `.c` *and* `.h` in the tool's directory, not
# just the file named after it -- `cg_input.c` includes `input_flags.h`, and a
# fix that lands only in the header would otherwise never be built.
#
# Failure is loud and fatal. A tool that cannot be rebuilt leaves the old binary
# in place, and the old binary is exactly what this exists to stop running; a
# launcher that carried on would be choosing the silent-corruption case. Note
# clang is only invoked when something is actually out of date, so a machine
# with current binaries and no compiler still starts a run.

set -e
cd "${0:A:h}"

# name:extra clang flags:whether it needs the task_for_pid entitlements.
# The flags are MACOS.md's, kept in step with it by
# tests/test_native_tools_are_built.py rather than by memory.
tools=(
    "probe::yes"
    "memory_sample::yes"
    "live_reader:-O2:yes"
    "tree_walker:-O2:yes"
    "window_probe:-framework ApplicationServices:no"
    "cg_input:-O2 -framework ApplicationServices:no"
    "cg_record:-O2 -framework ApplicationServices:no"
)

rebuilt=0
for entry in "${tools[@]}"; do
    name="${entry%%:*}"
    rest="${entry#*:}"
    flags="${rest%%:*}"
    entitled="${rest##*:}"

    binary="${name}/${name}"
    [[ -d "$name" ]] || { echo "build_tools: no directory ${name}" >&2; exit 1; }

    # Rebuild when the binary is missing, or when any source beside it is
    # newer. `-nt` is false for equal timestamps, which is the right way round:
    # a binary built in the same second as its source was built from it.
    stale=0
    [[ -x "$binary" ]] || stale=1
    if [[ $stale -eq 0 ]]; then
        for source in "${name}"/*.c(N) "${name}"/*.h(N); do
            [[ "$source" -nt "$binary" ]] && stale=1
        done
    fi
    [[ $stale -eq 0 ]] && continue

    echo "build_tools: rebuilding ${name}"
    # shellcheck disable=SC2086
    clang ${=flags} -o "$binary" "${name}/${name}.c"
    if [[ "$entitled" == "yes" ]]; then
        codesign -s - --entitlements "${name}/entitlements.plist" -f "$binary"
    else
        codesign -s - -f "$binary"
    fi
    rebuilt=$((rebuilt + 1))
done

[[ $rebuilt -gt 0 ]] && echo "build_tools: ${rebuilt} tool(s) rebuilt"
exit 0
