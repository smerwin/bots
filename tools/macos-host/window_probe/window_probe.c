// Window discovery probe: given a target PID (or, if omitted, scans all
// on-screen windows), lists each window's number, owner, layer, and bounds
// (in points, matching the coordinate space CGEventPost/CGWindowListCreateImage
// use), plus the backing scale factor of the display it's on. This is the
// macOS analog of `ListGameClientProcessesRequest` in the Elm bot's
// VolatileProcessInterface: it locates the EVE game window's on-screen frame
// without needing Accessibility API permission.
#include <ApplicationServices/ApplicationServices.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static double backing_scale_for_display(CGDirectDisplayID display) {
    CGDisplayModeRef mode = CGDisplayCopyDisplayMode(display);
    if (!mode) return 1.0;
    size_t pixel_w = CGDisplayModeGetPixelWidth(mode);
    size_t point_w = CGDisplayModeGetWidth(mode);
    CGDisplayModeRelease(mode);
    if (point_w == 0) return 1.0;
    return (double)pixel_w / (double)point_w;
}

static CGDirectDisplayID display_containing_point(CGFloat x, CGFloat y) {
    CGDirectDisplayID displays[16];
    uint32_t count = 0;
    CGGetDisplaysWithPoint(CGPointMake(x, y), 16, displays, &count);
    if (count > 0) return displays[0];
    return CGMainDisplayID();
}

static void print_string_field(CFDictionaryRef info, CFStringRef key, const char *label) {
    CFStringRef value = CFDictionaryGetValue(info, key);
    if (value && CFGetTypeID(value) == CFStringGetTypeID()) {
        char buf[512];
        if (CFStringGetCString(value, buf, sizeof(buf), kCFStringEncodingUTF8)) {
            printf("%s=\"%s\" ", label, buf);
            return;
        }
    }
    printf("%s=(null) ", label);
}

int main(int argc, char **argv) {
    pid_t filter_pid = -1;
    int all_spaces = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--all") == 0) {
            all_spaces = 1;
        } else {
            filter_pid = atoi(argv[i]);
        }
    }

    // --all (kCGWindowListOptionAll): includes windows on other macOS
    // Spaces (e.g. a fullscreen game), which kCGWindowListOptionOnScreenOnly
    // cannot see at all. Bounds are still populated correctly for those --
    // confirmed empirically, no need to switch Spaces just to read a
    // window's rect. Default stays on-screen-only since that's what
    // interactive use (picking a window to screencapture) wants.
    CGWindowListOption listOptions = all_spaces
        ? kCGWindowListOptionAll
        : (kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements);

    CFArrayRef windows = CGWindowListCopyWindowInfo(listOptions, kCGNullWindowID);
    if (!windows) {
        fprintf(stderr, "CGWindowListCopyWindowInfo returned NULL\n");
        return 1;
    }

    CFIndex n = CFArrayGetCount(windows);
    int matches = 0;

    for (CFIndex i = 0; i < n; i++) {
        CFDictionaryRef info = CFArrayGetValueAtIndex(windows, i);

        CFNumberRef owner_pid_ref = CFDictionaryGetValue(info, kCGWindowOwnerPID);
        pid_t owner_pid = -1;
        if (owner_pid_ref) CFNumberGetValue(owner_pid_ref, kCFNumberIntType, &owner_pid);

        if (filter_pid != -1 && owner_pid != filter_pid) continue;

        CFNumberRef win_num_ref = CFDictionaryGetValue(info, kCGWindowNumber);
        int win_num = -1;
        if (win_num_ref) CFNumberGetValue(win_num_ref, kCFNumberIntType, &win_num);

        CFNumberRef layer_ref = CFDictionaryGetValue(info, kCGWindowLayer);
        int layer = -1;
        if (layer_ref) CFNumberGetValue(layer_ref, kCFNumberIntType, &layer);

        CGRect bounds = CGRectZero;
        CFDictionaryRef bounds_dict = CFDictionaryGetValue(info, kCGWindowBounds);
        if (bounds_dict) CGRectMakeWithDictionaryRepresentation(bounds_dict, &bounds);

        printf("window=%d owner_pid=%d layer=%d ", win_num, owner_pid, layer);
        print_string_field(info, kCGWindowOwnerName, "owner");
        print_string_field(info, kCGWindowName, "name");
        printf("bounds={x=%.1f y=%.1f w=%.1f h=%.1f}(points) ",
               bounds.origin.x, bounds.origin.y, bounds.size.width, bounds.size.height);

        CGDirectDisplayID display = display_containing_point(
            bounds.origin.x + bounds.size.width / 2,
            bounds.origin.y + bounds.size.height / 2);
        double scale = backing_scale_for_display(display);
        printf("display=%u backing_scale=%.2f\n", display, scale);

        matches++;
    }

    CFRelease(windows);

    if (matches == 0) {
        fprintf(stderr, "no matching windows found%s\n",
                filter_pid != -1 ? " for that pid" : "");
        return 1;
    }
    return 0;
}
