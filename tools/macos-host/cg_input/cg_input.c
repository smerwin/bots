// Executes mouse/keyboard input via CGEventPost -- the macOS analog of
// the Windows WindowsInputSequenceItem execution BotLab.exe does natively.
// Persistent process (like live_reader): reads one text command per line
// from stdin, executes it, prints "ok" or "err <message>" to stdout.
//
// Commands (coordinates in points, the same space window_probe reports):
//   move <x> <y>              mouse move (no button held)
//   down <button>             mouse button down at last-known position (0=left 1=right 2=other)
//   up <button>                mouse button up at last-known position
//   drag <x> <y> <button>      mouse move while <button> is held (drag event)
//   idle                       seconds since the last real (hardware) input
//   doubleclick <button>       double click at last-known position
//   keydown <keyCode>          key down (macOS virtual keycode, CGKeyCode)
//   keyup <keyCode>            key up
//   text <utf8>                type literal text (by character, not keycode)
//   scroll <dx> <dy>           scroll wheel event
//
// `--dry-run` composes and reports every event without posting any of them:
// each one prints `post <kind> <code> flags=0x...` before its `ok`. That is how
// the flag composition below is tested, because the alternative -- posting real
// events from a test -- would drive whatever is frontmost, and on this machine
// that is usually a live client.
//
// `doubleclick` is its own command rather than two `down`/`up` pairs because
// two ordinary clicks in a row are not a double click, however fast they are
// sent: what makes the second one count is the kCGMouseEventClickState field,
// which has to say 2. Without it the application receives two independent
// single clicks and no double-click action ever fires.
//
// Requires Accessibility permission granted to whatever process runs this
// (System Settings -> Privacy & Security -> Accessibility) -- CGEventPost
// silently does nothing without it.
#include <ApplicationServices/ApplicationServices.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <IOKit/hidsystem/IOLLEvent.h>

#include "input_flags.h"

// input_flags.h restates these so it can be compiled and tested anywhere. Here
// is where they are held to the system's own values.
_Static_assert(CGI_FLAG_CAPSLOCK == kCGEventFlagMaskAlphaShift, "caps lock bit");
_Static_assert(CGI_FLAG_SHIFT == kCGEventFlagMaskShift, "shift bit");
_Static_assert(CGI_FLAG_CONTROL == kCGEventFlagMaskControl, "control bit");
_Static_assert(CGI_FLAG_OPTION == kCGEventFlagMaskAlternate, "option bit");
_Static_assert(CGI_FLAG_COMMAND == kCGEventFlagMaskCommand, "command bit");
_Static_assert(CGI_FLAG_HELP == kCGEventFlagMaskHelp, "help bit");
_Static_assert(CGI_FLAG_FN == kCGEventFlagMaskSecondaryFn, "fn bit");
_Static_assert(CGI_DEVICE_LCONTROL == NX_DEVICELCTLKEYMASK, "left control bit");
_Static_assert(CGI_DEVICE_RCONTROL == NX_DEVICERCTLKEYMASK, "right control bit");
_Static_assert(CGI_DEVICE_LSHIFT == NX_DEVICELSHIFTKEYMASK, "left shift bit");
_Static_assert(CGI_DEVICE_RSHIFT == NX_DEVICERSHIFTKEYMASK, "right shift bit");
_Static_assert(CGI_DEVICE_LCOMMAND == NX_DEVICELCMDKEYMASK, "left command bit");
_Static_assert(CGI_DEVICE_RCOMMAND == NX_DEVICERCMDKEYMASK, "right command bit");
_Static_assert(CGI_DEVICE_LOPTION == NX_DEVICELALTKEYMASK, "left option bit");
_Static_assert(CGI_DEVICE_ROPTION == NX_DEVICERALTKEYMASK, "right option bit");
_Static_assert(CGI_DEVICE_CAPSLOCK == NX_DEVICE_ALPHASHIFT_STATELESS_MASK,
               "caps lock device bit");
// The one bit inside the low byte that is not a modifier, and so must stay
// outside CGI_MANAGED_MODIFIERS.
_Static_assert((CGI_MANAGED_MODIFIERS & NX_NONCOALSESCEDMASK) == 0,
               "non-coalesced is not a modifier");

static CGPoint lastPos = {0, 0};

// The modifiers *this process* is holding, maintained from the keydown and
// keyup commands it is given. Every posted event carries these and nothing
// else -- see postEvent.
static uint64_t heldModifiers = 0;

static int dryRun = 0;

static CGMouseButton buttonFromInt(int b) {
    if (b == 1) return kCGMouseButtonRight;
    if (b == 2) return kCGMouseButtonCenter;
    return kCGMouseButtonLeft;
}

// The single exit. Every event this file creates leaves through here, because
// what has to be true of all of them is true of none of them by default.
//
// An event created with a NULL source is born carrying the session's current
// modifier state rather than an empty one -- measured on this machine, an
// unposted CGEventCreateKeyboardEvent(NULL, ...) reads back 0x20800100, which
// is kCGEventFlagMaskSecondaryFn set. That machine reports Fn/Globe held
// permanently with nobody at the keyboard, so before #240 every key the bot
// pressed was a Globe chord: Q is Quick Note, E the emoji picker, C Control
// Centre, F toggle-full-screen. Mouse events inherit the same way, and a click
// carrying a stray Control is a *secondary* click -- a context menu where the
// bot meant to select.
//
// Clearing the flags outright would be the other half of the bug: Ctrl+click
// is how the bot locks a target and Ctrl+Shift+click is how it unlocks, and
// `lockClickLocationFromStepEffects` recognises a lock attempt by exactly that
// chord. So what is posted is what we are holding, taken from the keydown and
// keyup commands we were given rather than from the session.
static void postEvent(CGEventRef event, const char *kind, long long code) {
    CGEventFlags born = CGEventGetFlags(event);
    CGEventSetFlags(event, (CGEventFlags)cgi_compose((uint64_t)born, heldModifiers));
    if (dryRun) {
        // `born` is what the session handed us and is reported alongside the
        // composed flags, so a reader can see what was taken off as well as
        // what went on.
        printf("post %s %lld born=0x%llx flags=0x%llx\n", kind, code,
               (unsigned long long)born,
               (unsigned long long)CGEventGetFlags(event));
    } else {
        CGEventPost(kCGHIDEventTap, event);
    }
}

static void postMouse(CGEventType type, CGPoint point, CGMouseButton button) {
    CGEventRef event = CGEventCreateMouseEvent(NULL, type, point, button);
    postEvent(event, "mouse", (long long)button);
    CFRelease(event);
    lastPos = point;
}

// Same as postMouse, but stamping the click number the window server uses to
// decide whether a press is a fresh click or a continuation of the previous
// one. 1 then 2 across two press/release pairs is what an application reads as
// a double click.
static void postMouseWithClickState(CGEventType type, CGPoint point,
                                    CGMouseButton button, int64_t clickState) {
    CGEventRef event = CGEventCreateMouseEvent(NULL, type, point, button);
    CGEventSetIntegerValueField(event, kCGMouseEventClickState, clickState);
    postEvent(event, "mouse", (long long)button);
    CFRelease(event);
    lastPos = point;
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--dry-run") == 0) {
            dryRun = 1;
        } else {
            fprintf(stderr, "cg_input: unknown argument %s\n", argv[i]);
            return 2;
        }
    }

    char line[256];
    while (fgets(line, sizeof(line), stdin)) {
        char cmd[32];
        double a1 = 0, a2 = 0;
        int ib = 0;

        if (sscanf(line, "%31s %lf %lf", cmd, &a1, &a2) >= 1) {
            if (strcmp(cmd, "move") == 0) {
                CGPoint p = {a1, a2};
                postMouse(kCGEventMouseMoved, p, kCGMouseButtonLeft);
                printf("ok\n");
            } else if (strcmp(cmd, "down") == 0) {
                ib = (int)a1;
                CGMouseButton btn = buttonFromInt(ib);
                CGEventType type = ib == 1 ? kCGEventRightMouseDown : kCGEventLeftMouseDown;
                postMouse(type, lastPos, btn);
                printf("ok\n");
            } else if (strcmp(cmd, "up") == 0) {
                ib = (int)a1;
                CGMouseButton btn = buttonFromInt(ib);
                CGEventType type = ib == 1 ? kCGEventRightMouseUp : kCGEventLeftMouseUp;
                postMouse(type, lastPos, btn);
                printf("ok\n");
            } else if (strcmp(cmd, "drag") == 0) {
                char cmd2[32];
                double x, y;
                int btn;
                if (sscanf(line, "%31s %lf %lf %d", cmd2, &x, &y, &btn) == 4) {
                    CGPoint p = {x, y};
                    CGEventType type = btn == 1 ? kCGEventRightMouseDragged : kCGEventLeftMouseDragged;
                    postMouse(type, p, buttonFromInt(btn));
                    printf("ok\n");
                } else {
                    printf("err bad drag args\n");
                }
            } else if (strcmp(cmd, "doubleclick") == 0) {
                ib = (int)a1;
                CGMouseButton btn = buttonFromInt(ib);
                CGEventType downType = ib == 1 ? kCGEventRightMouseDown : kCGEventLeftMouseDown;
                CGEventType upType = ib == 1 ? kCGEventRightMouseUp : kCGEventLeftMouseUp;
                postMouseWithClickState(downType, lastPos, btn, 1);
                postMouseWithClickState(upType, lastPos, btn, 1);
                postMouseWithClickState(downType, lastPos, btn, 2);
                postMouseWithClickState(upType, lastPos, btn, 2);
                printf("ok\n");
            } else if (strcmp(cmd, "keydown") == 0 || strcmp(cmd, "keyup") == 0) {
                CGKeyCode key = (CGKeyCode)a1;
                bool down = strcmp(cmd, "keydown") == 0;
                // Before the event is stamped, so that the modifier keydown
                // carries its own bit and its keyup does not -- which is what
                // the same press does in hardware.
                heldModifiers = cgi_hold(heldModifiers, (uint16_t)key, down);
                CGEventRef event = CGEventCreateKeyboardEvent(NULL, key, down);
                postEvent(event, down ? "key" : "keyup", (long long)key);
                CFRelease(event);
                printf("ok\n");
            } else if (strcmp(cmd, "text") == 0) {
                // Type literal text, one character per event, by payload rather
                // than by keycode.
                //
                // Keycodes are how every other key here is sent, and for text
                // they are not reliable against this client: driving the search
                // field a character at a time, 'a' (keycode 0) never arrived at
                // all across five retries, and 'h', 'c', 'n' and 's' dropped
                // intermittently while 'z', 'i', 'o' and 'r' were perfect. Same
                // window, same focus, same pacing.
                //
                // CGEventKeyboardSetUnicodeString should sidestep the whole
                // question: the event carries the character itself, so nothing
                // depends on a keycode being mapped or on the keyboard layout.
                //
                // It does not work on the EVE client. Tested against a focused
                // search field, a single 'z' sent this way arrives as nothing at
                // all, while the same character sent by keycode arrives every
                // time. The client evidently reads keycodes and ignores the
                // unicode payload, which is usual for games taking input at a
                // low level. Kept because the command is correct and may serve
                // another application; do not reach for it here.
                char *rest = line + 4;
                while (*rest == ' ') rest++;
                size_t n = strlen(rest);
                while (n && (rest[n - 1] == '\n' || rest[n - 1] == '\r')) rest[--n] = '\0';

                CFStringRef str = CFStringCreateWithCString(NULL, rest, kCFStringEncodingUTF8);
                if (!str) {
                    printf("err bad utf8\n");
                } else {
                    CFIndex count = CFStringGetLength(str);
                    for (CFIndex i = 0; i < count; i++) {
                        UniChar ch = CFStringGetCharacterAtIndex(str, i);
                        CGEventRef down = CGEventCreateKeyboardEvent(NULL, 0, true);
                        CGEventKeyboardSetUnicodeString(down, 1, &ch);
                        postEvent(down, "text", (long long)ch);
                        CFRelease(down);

                        CGEventRef up = CGEventCreateKeyboardEvent(NULL, 0, false);
                        CGEventKeyboardSetUnicodeString(up, 1, &ch);
                        postEvent(up, "text", (long long)ch);
                        CFRelease(up);
                    }
                    CFRelease(str);
                    printf("ok\n");
                }
            } else if (strcmp(cmd, "idle") == 0) {
                // Seconds since the last *hardware* input event. Asking the HID
                // state specifically is what makes this usable: events we post
                // ourselves with CGEventPost do not update it, so this measures
                // the human at the keyboard rather than the bot's own clicking.
                // Combined session state would count both and always read ~0.
                double idle = CGEventSourceSecondsSinceLastEventType(
                    kCGEventSourceStateHIDSystemState, kCGAnyInputEventType);
                printf("idle %.3f\n", idle);
            } else if (strcmp(cmd, "scroll") == 0) {
                CGEventRef event = CGEventCreateScrollWheelEvent(
                    NULL, kCGScrollEventUnitLine, 2, (int32_t)a2, (int32_t)a1);
                postEvent(event, "scroll", 0);
                CFRelease(event);
                printf("ok\n");
            } else {
                printf("err unknown command\n");
            }
        } else {
            printf("err parse\n");
        }
        fflush(stdout);
    }
    return 0;
}
