// The modifier mask cg_input stamps on every event it posts.
//
// Split out of cg_input.c so it can be executed on a machine with no
// CoreGraphics -- the composition rule is the whole of the fix for #240 and it
// is worth checking on every push rather than only where clang can link
// ApplicationServices.
//
// The bit values are restated here rather than included from
// ApplicationServices. cg_input.c static-asserts each one against the
// framework's own constant, so a divergence is a build failure on macOS rather
// than a wrong mask at run time.
#ifndef CG_INPUT_INPUT_FLAGS_H
#define CG_INPUT_INPUT_FLAGS_H

#include <stdint.h>

// The device-independent half: which modifier is held.
#define CGI_FLAG_CAPSLOCK 0x00010000ULL
#define CGI_FLAG_SHIFT    0x00020000ULL
#define CGI_FLAG_CONTROL  0x00040000ULL
#define CGI_FLAG_OPTION   0x00080000ULL
#define CGI_FLAG_COMMAND  0x00100000ULL
#define CGI_FLAG_HELP     0x00400000ULL
#define CGI_FLAG_FN       0x00800000ULL

// The device-dependent half: which physical key is holding it. Both halves
// have to be managed together. A session that reports a stray Control reports
// it twice -- 0x00040000 and 0x00000001 -- and an event that carries only the
// second one is still a Control-click to anything that reads events at the
// level this client does.
#define CGI_DEVICE_LCONTROL 0x00000001ULL
#define CGI_DEVICE_LSHIFT   0x00000002ULL
#define CGI_DEVICE_RSHIFT   0x00000004ULL
#define CGI_DEVICE_LCOMMAND 0x00000008ULL
#define CGI_DEVICE_RCOMMAND 0x00000010ULL
#define CGI_DEVICE_LOPTION  0x00000020ULL
#define CGI_DEVICE_ROPTION  0x00000040ULL
#define CGI_DEVICE_CAPSLOCK 0x00000080ULL
#define CGI_DEVICE_RCONTROL 0x00002000ULL

// The bits this process owns: every modifier a key can hold down, in both
// halves. They are cleared on the way out and replaced by what we are actually
// holding.
//
// Everything outside this mask is left exactly as the event carries it,
// because those bits describe the *event* rather than a held key --
// kCGEventFlagMaskNumericPad says the keycode is an arrow or a keypad digit,
// and kCGEventFlagMaskNonCoalesced (0x100) says the window server must not
// merge this mouse move into the next one, which this host depends on for the
// sustained hover the client needs.
#define CGI_MANAGED_MODIFIERS                                                 \
    (CGI_FLAG_CAPSLOCK | CGI_FLAG_SHIFT | CGI_FLAG_CONTROL |                  \
     CGI_FLAG_OPTION | CGI_FLAG_COMMAND | CGI_FLAG_HELP | CGI_FLAG_FN |       \
     CGI_DEVICE_LCONTROL | CGI_DEVICE_LSHIFT | CGI_DEVICE_RSHIFT |            \
     CGI_DEVICE_LCOMMAND | CGI_DEVICE_RCOMMAND | CGI_DEVICE_LOPTION |         \
     CGI_DEVICE_ROPTION | CGI_DEVICE_CAPSLOCK | CGI_DEVICE_RCONTROL)

// The modifier a macOS virtual keycode holds down while it is pressed, or 0
// for a key that holds nothing. Both halves, so what is stamped on the events
// that follow is what the same key held down in hardware would put there.
//
// Caps Lock (0x39) is deliberately absent: it latches rather than being held,
// so a keydown of it does not mean "capitals from here on". Its bits are still
// in CGI_MANAGED_MODIFIERS, so a session with Caps Lock on cannot capitalise
// what the bot types.
static inline uint64_t cgi_flag_for_key(uint16_t key) {
    switch (key) {
        case 0x38: return CGI_FLAG_SHIFT   | CGI_DEVICE_LSHIFT;    // Shift
        case 0x3C: return CGI_FLAG_SHIFT   | CGI_DEVICE_RSHIFT;    // RightShift
        case 0x3B: return CGI_FLAG_CONTROL | CGI_DEVICE_LCONTROL;  // Control
        case 0x3E: return CGI_FLAG_CONTROL | CGI_DEVICE_RCONTROL;  // RightControl
        case 0x3A: return CGI_FLAG_OPTION  | CGI_DEVICE_LOPTION;   // Option
        case 0x3D: return CGI_FLAG_OPTION  | CGI_DEVICE_ROPTION;   // RightOption
        case 0x37: return CGI_FLAG_COMMAND | CGI_DEVICE_LCOMMAND;  // Command
        case 0x36: return CGI_FLAG_COMMAND | CGI_DEVICE_RCOMMAND;  // RightCommand
        case 0x3F: return CGI_FLAG_FN;                             // Fn / Globe
        default:   return 0;
    }
}

// `held` after a keydown (`down` non-zero) or keyup of `key`. A key that holds
// no modifier leaves the mask alone.
//
// Releasing one of a pair -- left Shift while right Shift is still down --
// clears the device-independent bit both of them share. Nothing can reach that
// state through this host: `_VK_TO_CGKEYCODE` in `botlab_host.py` has one
// keycode per modifier and they are all the left-hand ones.
static inline uint64_t cgi_hold(uint64_t held, uint16_t key, int down) {
    uint64_t bit = cgi_flag_for_key(key);
    if (bit == 0) {
        return held;
    }
    return down ? (held | bit) : (held & ~bit);
}

// The flags to post an event with: the ones we are holding, and none of the
// session's. `event_flags` is what the event was born with.
static inline uint64_t cgi_compose(uint64_t event_flags, uint64_t held) {
    return (event_flags & ~CGI_MANAGED_MODIFIERS) | (held & CGI_MANAGED_MODIFIERS);
}

#endif
