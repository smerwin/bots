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
//   scroll <dx> <dy>           scroll wheel event
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

static CGPoint lastPos = {0, 0};

static CGMouseButton buttonFromInt(int b) {
    if (b == 1) return kCGMouseButtonRight;
    if (b == 2) return kCGMouseButtonCenter;
    return kCGMouseButtonLeft;
}

static void postMouse(CGEventType type, CGPoint point, CGMouseButton button) {
    CGEventRef event = CGEventCreateMouseEvent(NULL, type, point, button);
    CGEventPost(kCGHIDEventTap, event);
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
    CGEventPost(kCGHIDEventTap, event);
    CFRelease(event);
    lastPos = point;
}

int main(void) {
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
                CGEventRef event = CGEventCreateKeyboardEvent(NULL, key, down);
                CGEventPost(kCGHIDEventTap, event);
                CFRelease(event);
                printf("ok\n");
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
                CGEventPost(kCGHIDEventTap, event);
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
