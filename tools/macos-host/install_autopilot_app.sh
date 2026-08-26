#!/bin/zsh
# Installs ~/Applications/Autopilot.app, so that Cmd-Space "autopilot" starts
# the warp-to-0 autopilot on the route already set in the game client.
#
# Run it once. Re-run it after moving this checkout, since the path to
# run_autopilot.sh is baked into the bundle at install time.
#
#     ./install_autopilot_app.sh            # install
#     ./install_autopilot_app.sh --uninstall
#
# WHY THE APP OPENS A TERMINAL RATHER THAN RUNNING THE BOT ITSELF
#
# Screen Recording and Accessibility are granted per *application*, and the
# bot needs both -- Screen Recording to read window titles, Accessibility for
# the memory reads that find the UI root and for cg_input to move the mouse
# (MACOS.md). A .app that ran botlab_host.py directly would be a new
# application as far as macOS is concerned: it would need its own two grants,
# and until it had them it would launch, read nothing useful and click nothing
# at all. That is the silent failure MACOS.md's troubleshooting section
# describes as "nothing happens with --execute-input".
#
# Asking a terminal to run the script instead means the bot runs under an
# application whose grants are already in place. Nothing new to approve, and
# nothing new that can be silently un-approved later.
#
# The visible window is the second reason. This bot takes over the real mouse
# and keyboard, so a way to watch what it is doing and stop it with Ctrl-C
# matters more here than a tidy launch.
#
# WHICH TERMINAL
#
# Having *a* terminal is not enough -- it has to be one that actually holds
# both grants, and on this machine (2026-08-25) Terminal.app held neither
# while iTerm2 held both. Launching through Terminal there got as far as
# finding the client process and then stopped, because with Screen Recording
# denied every window title reads `(null)`, the host's own window regex does
# not match that, and the run ends with "I did not find an EVE Online client
# process" -- an error naming something that was never the problem.
#
# So iTerm2 is preferred where it is installed. The grants are not probed
# here, though: they are checked by run_autopilot.sh itself on every launch,
# which is the only place that protects a hand-typed run as well as this one,
# and the only place that is still right if a grant is revoked later.
#
# WHY THE SCRIPT RUNS UNDER A LOGIN SHELL
#
# `zsh -c` does not read the profile, so PATH lacks Homebrew and `python3`
# resolves to /usr/bin/python3 -- which has no Pillow, so botlab_host.py dies
# on `from PIL import Image` before it does anything at all. Observed exactly
# once, and once was enough: the same script typed by hand in the same
# terminal worked, because an interactive shell is a login shell. `-l` is what
# makes the bundle behave like typing it.

set -e -u -o pipefail

SCRIPT_DIR="${0:A:h}"
RUN_SCRIPT="${SCRIPT_DIR}/run_autopilot.sh"
APP="${HOME}/Applications/Autopilot.app"

if [[ "${1-}" == "--uninstall" ]]; then
    if [[ -d "$APP" ]]; then
        rm -rf "$APP"
        echo "removed $APP"
    else
        echo "nothing to remove: $APP does not exist"
    fi
    exit 0
fi

if [[ ! -x "$RUN_SCRIPT" ]]; then
    echo "install_autopilot_app.sh: $RUN_SCRIPT is missing or not executable." >&2
    echo "  The bundle would install cleanly and then fail on every launch, so this stops here." >&2
    exit 1
fi

# A path with a double quote or a backslash in it would be interpolated into
# the AppleScript string literal below and break it -- refuse rather than
# install something that fails only when launched.
case "$RUN_SCRIPT" in
    *\"* | *\\*)
        echo "install_autopilot_app.sh: this checkout's path contains a quote or backslash:" >&2
        echo "  $RUN_SCRIPT" >&2
        echo "  The generated launcher cannot quote that safely. Move the checkout and re-run." >&2
        exit 1
        ;;
esac

mkdir -p "${APP}/Contents/MacOS"

cat > "${APP}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Autopilot</string>
    <key>CFBundleDisplayName</key>
    <string>Autopilot</string>
    <key>CFBundleIdentifier</key>
    <string>org.smerwin.bots.autopilot</string>
    <key>CFBundleExecutable</key>
    <string>Autopilot</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSBackgroundOnly</key>
    <false/>
</dict>
</plist>
PLIST

# `activate` first so the window comes to the front; without it the bot starts
# behind whatever you were looking at, which for something that is about to
# take the mouse is the wrong default.
#
# `zsh -lc` and not `zsh -c`: see the header. A non-login shell finds
# /usr/bin/python3, which has no Pillow, and the host dies on import.
if [[ -d /Applications/iTerm.app || -d "${HOME}/Applications/iTerm.app" ]]; then
    TERMINAL_APP="iTerm"
    cat > "${APP}/Contents/MacOS/Autopilot" <<LAUNCHER
#!/bin/zsh
exec /usr/bin/osascript \\
    -e 'tell application "iTerm" to activate' \\
    -e 'tell application "iTerm" to create window with default profile command "/bin/zsh -lc \\"${RUN_SCRIPT}\\""'
LAUNCHER
else
    TERMINAL_APP="Terminal"
    cat > "${APP}/Contents/MacOS/Autopilot" <<LAUNCHER
#!/bin/zsh
exec /usr/bin/osascript \\
    -e 'tell application "Terminal" to activate' \\
    -e 'tell application "Terminal" to do script "/bin/zsh -lc \\"${RUN_SCRIPT}\\""'
LAUNCHER
fi

chmod +x "${APP}/Contents/MacOS/Autopilot"

# Spotlight indexes ~/Applications, but a freshly written bundle can take a
# while to appear. Asking for it directly makes `Cmd-Space autopilot` work now
# rather than eventually.
/usr/bin/mdimport "$APP" 2>/dev/null || true

echo "installed $APP"
echo "  runs:     $RUN_SCRIPT"
echo "  through:  $TERMINAL_APP (a login shell, so PATH matches a typed run)"
echo "  Cmd-Space, type 'autopilot', Return."
