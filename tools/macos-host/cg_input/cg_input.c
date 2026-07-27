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
//   keydown <keyCode>          key down (macOS virtual keycode, CGKeyCode)
//   keyup <keyCode>            key up
//   scroll <dx> <dy>           scroll wheel event
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
            } else if (strcmp(cmd, "keydown") == 0 || strcmp(cmd, "keyup") == 0) {
                CGKeyCode key = (CGKeyCode)a1;
                bool down = strcmp(cmd, "keydown") == 0;
                CGEventRef event = CGEventCreateKeyboardEvent(NULL, key, down);
                CGEventPost(kCGHIDEventTap, event);
                CFRelease(event);
                printf("ok\n");
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
