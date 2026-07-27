#!/bin/zsh
# Collects a "process sample": a screenshot of the EVE game window plus a
# dump of the game client process's memory, taken close together in time so
# the two can be correlated later. macOS analog of the Windows
# `read-memory-64-bit.exe save-process-sample` tool described in
# guide/how-to-collect-samples-for-64-bit-memory-reading-development.md.
#
# On this machine the on-screen window and the memory-bearing process are
# different PIDs (see CLAUDE.md): the window belongs to the
# com.ccpgames.eve-online-launcher process, memory belongs to the
# com.ccpgames.eveonline (`exefile`) process. Pass both explicitly.
#
# Usage:
#   save_process_sample.sh --memory-pid=<pid> --window-pid=<pid> [--out=<dir>]

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
MEMORY_PID=""
WINDOW_PID=""
OUT_DIR=""

for arg in "$@"; do
    case "$arg" in
        --memory-pid=*) MEMORY_PID="${arg#*=}" ;;
        --window-pid=*) WINDOW_PID="${arg#*=}" ;;
        --out=*) OUT_DIR="${arg#*=}" ;;
        *)
            echo "unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$MEMORY_PID" || -z "$WINDOW_PID" ]]; then
    echo "usage: $0 --memory-pid=<pid> --window-pid=<pid> [--out=<dir>]" >&2
    exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$OUT_DIR" ]]; then
    OUT_DIR="process-sample-$TIMESTAMP"
fi
mkdir -p "$OUT_DIR"

# window_probe's output order is z-order, not size, and a fullscreen game
# window can be accompanied by smaller overlay windows (e.g. the reveal-on-hover
# menu bar strip) that sort earlier. Pick the largest layer=0 window instead of
# just the first line.
WINDOW_LINE=""
BEST_AREA=0
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    LAYER="$(echo "$line" | sed -n 's/.*layer=\(-\{0,1\}[0-9]*\).*/\1/p')"
    [[ "$LAYER" != "0" ]] && continue
    W="$(echo "$line" | sed -n 's/.*w=\([0-9.]*\).*/\1/p')"
    H="$(echo "$line" | sed -n 's/.*h=\([0-9.]*\).*/\1/p')"
    AREA="$(echo "$W * $H" | bc)"
    if (( $(echo "$AREA > $BEST_AREA" | bc -l) )); then
        BEST_AREA="$AREA"
        WINDOW_LINE="$line"
    fi
done <<< "$("$SCRIPT_DIR/window_probe/window_probe" "$WINDOW_PID")"
if [[ -z "$WINDOW_LINE" ]]; then
    echo "no on-screen layer=0 window found for window-pid=$WINDOW_PID" >&2
    exit 1
fi
echo "window: $WINDOW_LINE"

WINDOW_NUMBER="$(echo "$WINDOW_LINE" | sed -n 's/^window=\([0-9]*\).*/\1/p')"
if [[ -z "$WINDOW_NUMBER" ]]; then
    echo "could not parse window number from: $WINDOW_LINE" >&2
    exit 1
fi

SCREENSHOT_BEFORE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
screencapture -x -o -l "$WINDOW_NUMBER" "$OUT_DIR/screenshot.png"
SCREENSHOT_AFTER="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

MEMORY_BEFORE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$SCRIPT_DIR/memory_sample/memory_sample" "$MEMORY_PID" "$OUT_DIR" 2>"$OUT_DIR/memory_sample.log" || {
    echo "memory_sample failed, see $OUT_DIR/memory_sample.log" >&2
    cat "$OUT_DIR/memory_sample.log" >&2
    exit 1
}
MEMORY_AFTER="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat "$OUT_DIR/memory_sample.log"

MEMORY_SHA256="$(shasum -a 256 "$OUT_DIR/memory.bin" | awk '{print $1}')"
MEMORY_BYTES="$(stat -f%z "$OUT_DIR/memory.bin")"

cat > "$OUT_DIR/manifest.json" <<EOF
{
  "memory_pid": $MEMORY_PID,
  "window_pid": $WINDOW_PID,
  "window_number": $WINDOW_NUMBER,
  "screenshot": {
    "file": "screenshot.png",
    "started_at": "$SCREENSHOT_BEFORE",
    "finished_at": "$SCREENSHOT_AFTER"
  },
  "memory_dump": {
    "file": "memory.bin",
    "index_file": "regions.tsv",
    "started_at": "$MEMORY_BEFORE",
    "finished_at": "$MEMORY_AFTER",
    "sha256": "$MEMORY_SHA256",
    "bytes": $MEMORY_BYTES
  }
}
EOF

echo "sample written to $OUT_DIR"
echo "  screenshot.png"
echo "  memory.bin ($MEMORY_BYTES bytes, sha256 $MEMORY_SHA256)"
echo "  regions.tsv"
echo "  manifest.json"
