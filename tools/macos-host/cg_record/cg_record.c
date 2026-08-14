/* cg_record -- passive recorder for mouse and keyboard, macOS.
 *
 * The mirror of cg_input: where that one posts events, this one only listens.
 * One line per event on stdout, so the Python side can stay a line reader:
 *
 *     EVENT <monotonic_ms> <kind> <x> <y> <flags> <keycode>
 *
 * kind is one of: ldown lup rdown rup mdown mup key keyup scroll
 * x, y are screen points (the same units cg_input takes, so the two agree).
 * flags is the CGEventFlags bitmask, so modifiers are recoverable.
 * keycode is the CGKeyCode for key events and 0 otherwise.
 *
 * LISTEN ONLY, and that is load-bearing rather than incidental. The tap is
 * created with kCGEventTapOptionListenOnly, so it cannot alter, delay or
 * swallow an event -- a recorder that can drop the operator's clicks would be
 * worse than no recorder. It also means this is safe to leave running beside
 * anything else, including a bot session, though see the note in
 * action_shape.py about why you probably do not want to.
 *
 * Needs Accessibility permission for the terminal it runs from, the same grant
 * cg_input already needs. Without it CGEventTapCreate returns NULL and this
 * exits non-zero saying so, rather than sitting silently recording nothing --
 * which is the failure this repo keeps a section about.
 *
 * Build:
 *     clang -O2 -framework ApplicationServices -framework CoreFoundation \
 *         -o cg_record cg_record.c
 */

#include <ApplicationServices/ApplicationServices.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <mach/mach_time.h>

static double g_ms_per_tick = 0.0;

static double now_ms(void) {
    if (g_ms_per_tick == 0.0) {
        mach_timebase_info_data_t tb;
        mach_timebase_info(&tb);
        g_ms_per_tick = (double)tb.numer / (double)tb.denom / 1.0e6;
    }
    return (double)mach_absolute_time() * g_ms_per_tick;
}

static const char *kind_of(CGEventType t) {
    switch (t) {
        case kCGEventLeftMouseDown:   return "ldown";
        case kCGEventLeftMouseUp:     return "lup";
        case kCGEventRightMouseDown:  return "rdown";
        case kCGEventRightMouseUp:    return "rup";
        case kCGEventOtherMouseDown:  return "mdown";
        case kCGEventOtherMouseUp:    return "mup";
        case kCGEventKeyDown:         return "key";
        case kCGEventKeyUp:           return "keyup";
        case kCGEventScrollWheel:     return "scroll";
        default:                      return NULL;
    }
}

static CGEventRef on_event(CGEventTapProxy proxy, CGEventType type,
                           CGEventRef event, void *refcon) {
    (void)proxy; (void)refcon;

    /* The system disables a tap that is too slow, or on an input-source
     * change. Say so and re-enable, rather than going quiet -- a recorder
     * that stops recording and keeps running looks exactly like a session in
     * which the operator did nothing. */
    if (type == kCGEventTapDisabledByTimeout ||
        type == kCGEventTapDisabledByUserInput) {
        fprintf(stderr, "# tap disabled (%d); re-enabling\n", (int)type);
        fflush(stderr);
        return event;
    }

    const char *kind = kind_of(type);
    if (kind != NULL) {
        CGPoint p = CGEventGetLocation(event);
        CGEventFlags flags = CGEventGetFlags(event);
        int64_t keycode = 0;
        if (type == kCGEventKeyDown || type == kCGEventKeyUp) {
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
        }
        printf("EVENT %.1f %s %.1f %.1f %llu %lld\n",
               now_ms(), kind, p.x, p.y,
               (unsigned long long)flags, (long long)keycode);
        fflush(stdout);
    }
    return event;
}

int main(void) {
    CGEventMask mask =
        CGEventMaskBit(kCGEventLeftMouseDown)  | CGEventMaskBit(kCGEventLeftMouseUp)  |
        CGEventMaskBit(kCGEventRightMouseDown) | CGEventMaskBit(kCGEventRightMouseUp) |
        CGEventMaskBit(kCGEventOtherMouseDown) | CGEventMaskBit(kCGEventOtherMouseUp) |
        CGEventMaskBit(kCGEventKeyDown)        | CGEventMaskBit(kCGEventKeyUp)        |
        CGEventMaskBit(kCGEventScrollWheel);

    CFMachPortRef tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        on_event,
        NULL);

    if (tap == NULL) {
        fprintf(stderr,
                "cg_record: CGEventTapCreate returned NULL.\n"
                "This is almost always the Accessibility permission missing for\n"
                "the terminal you are running from -- the same grant cg_input\n"
                "needs. System Settings > Privacy & Security > Accessibility.\n");
        return 2;
    }

    CFRunLoopSourceRef src = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0);
    CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes);
    CGEventTapEnable(tap, true);

    fprintf(stderr, "# cg_record: listening (listen-only tap)\n");
    fflush(stderr);

    CFRunLoopRun();

    CFRelease(src);
    CFRelease(tap);
    return 0;
}
