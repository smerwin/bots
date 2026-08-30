#!/bin/zsh
# Compile a bot the way botlab_host.py does, without running it.
#
#   ./compile_bot.sh                       # every EVE app that has a Bot.elm
#   ./compile_bot.sh eve-online-saxrat     # one, by directory name or path
#
# The steps are the same ones botlab_host.py performs before every run: copy the
# app to a scratch directory, drop in the host's Main.elm port wrapper, patch
# elm-version, and build. Doing it here means a type error surfaces in a second
# rather than after killing a live session.
#
# Why a script rather than four commands typed by hand: the copy is the trap.
# Editing a bot and then building a scratch copy that did not receive the edit
# reports success for code that was never compiled -- which happened, and cost a
# round of believing a broken change was fine. So the copy is verified against
# the source afterwards, and any file that differs is a hard failure. The only
# permitted difference is elm.json's elm-version, which is patched on purpose.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
APPS_DIR="${SCRIPT_DIR}/../../implement/applications/eve-online"
MAIN_ELM="${SCRIPT_DIR}/botlab_host/Main.elm"

# Which wrapper a bot needs is fixed by the interface its own Bot.elm imports.
# Mirrors MAIN_ELM_TEMPLATE_BY_INTERFACE in botlab_host.py -- keep the two in
# step, or this verifies a build the host would never produce. There is one
# wrapper now, and the `case` is kept rather than flattened for the same reason
# the host keeps a map: an app on an interface with no wrapper is *skipped and
# named* rather than built against the wrong one.
main_elm_for() {
    case "$(grep -m1 -o 'BotLab\.BotInterface_To_Host_[0-9_]*' "$1/Bot.elm")" in
        BotLab.BotInterface_To_Host_2024_10_19) print -r -- "$MAIN_ELM" ;;
        *) return 1 ;;
    esac
}
BUILD_ROOT="${TMPDIR:-/tmp}/compile_bot"

if ! command -v elm > /dev/null; then
    print -u2 "elm is not on PATH -- brew install elm (not npm, see MACOS.md)"
    exit 1
fi

# Homebrew's elm reports 0.19.2 while every checked-in elm.json pins 0.19.1, and
# an application-type elm.json demands an exact match. Patch the copy, never the
# source.
ELM_VERSION="$(elm --version)"

if (( $# > 0 )); then
    targets=("$@")
else
    targets=()
    for candidate in "${APPS_DIR}"/*/; do
        [[ -f "${candidate}Bot.elm" ]] && targets+=("${candidate:A:t}")
    done
fi

failed=0
for target in "${targets[@]}"; do
    if [[ -d "$target" ]]; then
        src="${target:A}"
    else
        src="${APPS_DIR}/${target}"
    fi
    name="${src:t}"

    if [[ ! -f "$src/Bot.elm" ]]; then
        printf "  %-32s no Bot.elm, skipped\n" "$name"
        continue
    fi

    if ! main_elm="$(main_elm_for "$src")"; then
        printf "  %-32s no wrapper for its host interface, skipped\n" "$name"
        continue
    fi

    build="${BUILD_ROOT}/${name}"
    mkdir -p "$build"
    rsync -a --delete --exclude elm-stuff --exclude Main.elm "$src/" "$build/"
    cp "$main_elm" "$build/Main.elm"
    sed -i '' "s/\"0\.19\.[0-9]*\"/\"${ELM_VERSION}\"/" "$build/elm.json"

    # The copy must be the source. elm.json is expected to differ by exactly the
    # version patch above; anything else means the build is not testing what is
    # on disk.
    if ! diff -r -q --exclude elm-stuff --exclude Main.elm --exclude elm.json \
            "$src" "$build" > /dev/null; then
        printf "  %-32s COPY MISMATCH -- build would not reflect the source\n" "$name"
        diff -r -q --exclude elm-stuff --exclude Main.elm --exclude elm.json "$src" "$build" | sed 's/^/      /'
        failed=1
        continue
    fi

    if output="$(cd "$build" && elm make Main.elm --output=/dev/null 2>&1)"; then
        printf "  %-32s ok\n" "$name"
    else
        printf "  %-32s FAILED\n" "$name"
        print -r -- "$output" | tail -25 | sed 's/^/      /'
        failed=1
    fi
done

exit $failed
