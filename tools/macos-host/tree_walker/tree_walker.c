// Native (C) UI-tree walker: does the *entire* memory-read + CPython
// struct decode + tree assembly in one process, attached directly to the
// target via task_for_pid/mach_vm_read_overwrite -- no pipe protocol for
// the hot path at all (unlike live_reader.c, which serves individual
// reads to a separate Python process over a pipe). Built after profiling
// showed the Python implementation (re_helper.py's build_tree) had
// become genuinely CPU-bound on CPython interpreter overhead (millions
// of small Python-level operations: struct pack/unpack, list/dict
// operations) once round-trip count and data volume were no longer the
// bottleneck -- see CLAUDE.md. Moving the walk in-process eliminates
// both the interpreter overhead AND the pipe IPC boundary entirely; each
// "read" here is a plain C function call plus a microsecond-scale
// syscall, not a round trip to a separate process.
//
// This reimplements, in C, every struct layout confirmed by hand during
// this project's reverse-engineering (see CLAUDE.md for the full
// derivation of each offset -- this file assumes that work, it doesn't
// re-derive it):
//   - PyObject header: refcnt @0x00, ob_type @0x08
//   - Widget wrapper: + dict_ptr @0x10, weakref @0x18 (32 bytes)
//   - PyTypeObject: + ob_size @0x10, tp_name @0x18 (C string pointer)
//   - type-metaclass invariant: a real PyTypeObject's own ob_type
//     equals a single process-wide metatype address
//   - custom dict: header 0x38 (56) bytes -- refcnt, ob_type, two count
//     fields, capacity mask, overflow-table pointer, a shared/constant
//     vtable pointer -- then 8 inline (hash:8,key:8,value:8) 24-byte
//     entries, plus an external overflow table (same 24-byte entry
//     format) sized (mask+1) entries when present. Duplicate keys across
//     inline/overflow are possible; ordinary attributes use
//     last-occurrence-wins (overflow, walked after inline, wins), the
//     'children' key uses first-occurrence-wins -- matching the
//     Python implementation's behavior exactly (see CLAUDE.md for why
//     this asymmetry is intentional, not a bug).
//   - PyASCIIObject (compact 'str'): refcnt, ob_type, length @0x10,
//     hash @0x18, 4-byte state, ASCII bytes starting @0x24
//   - Python-2-style PyIntObject: refcnt, ob_type, signed ob_ival @0x10
//   - Python-2-style PyLongObject: refcnt, ob_type, signed ob_size
//     (digit count+sign) @0x10, 30-bit digits (4 bytes each) from @0x18
//   - Python-2-style PyUnicodeObject: refcnt, ob_type, length @0x10,
//     external UCS-4 buffer pointer @0x18, hash @0x20
//   - PyFloatObject: refcnt, ob_type, double ob_fval @0x10
//   - children resolution: obj.__dict__['children'] -> a PyChildrenList
//     wrapper (same 32-byte shape) -> its own
//     __dict__['_childrenObjects'] -> a genuine stock CPython
//     PyListObject (refcnt, ob_type, ob_size @0x10, ob_item pointer
//     @0x18, allocated @0x20) -> ob_item is a flat array of ob_size
//     8-byte child pointers
//
// Wire protocol, binary, over stdin/stdout (same persistent-process
// style as live_reader.c):
//   request:  8B root_addr, 8B metatype_addr, 8B str_type_addr,
//             4B max_depth, 4B max_nodes   (32 bytes)
//   response: 8B json_length (LE u64), then that many bytes of UTF-8 JSON
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdbool.h>

static task_t g_task;
static uint64_t g_metatype;

// ---------------------------------------------------------------------
// Growable output buffer
// ---------------------------------------------------------------------
typedef struct {
    unsigned char *data;
    size_t len;
    size_t cap;
} Buf;

static void buf_init(Buf *b) {
    b->cap = 1 << 20;
    b->data = malloc(b->cap);
    b->len = 0;
}

static void buf_ensure(Buf *b, size_t extra) {
    if (b->len + extra <= b->cap) return;
    while (b->len + extra > b->cap) b->cap *= 2;
    b->data = realloc(b->data, b->cap);
}

static void buf_append(Buf *b, const void *p, size_t n) {
    buf_ensure(b, n);
    memcpy(b->data + b->len, p, n);
    b->len += n;
}

static void buf_str(Buf *b, const char *s) { buf_append(b, s, strlen(s)); }

static void buf_json_escape(Buf *b, const unsigned char *s, size_t n) {
    buf_ensure(b, n * 6 + 2);
    b->data[b->len++] = '"';
    for (size_t i = 0; i < n; i++) {
        unsigned char c = s[i];
        if (c == '"' || c == '\\') {
            b->data[b->len++] = '\\';
            b->data[b->len++] = c;
        } else if (c == '\n') {
            b->data[b->len++] = '\\'; b->data[b->len++] = 'n';
        } else if (c == '\r') {
            b->data[b->len++] = '\\'; b->data[b->len++] = 'r';
        } else if (c == '\t') {
            b->data[b->len++] = '\\'; b->data[b->len++] = 't';
        } else if (c < 0x20) {
            char tmp[8];
            int k = snprintf(tmp, sizeof(tmp), "\\u%04x", c);
            memcpy(b->data + b->len, tmp, k);
            b->len += k;
        } else {
            b->data[b->len++] = c;
        }
    }
    b->data[b->len++] = '"';
}

// utf-32-le codepoints -> utf-8 json string (unicode attribute values)
static void buf_json_escape_utf32(Buf *b, const uint32_t *cp, size_t n) {
    buf_ensure(b, n * 6 + 2);
    b->data[b->len++] = '"';
    for (size_t i = 0; i < n; i++) {
        uint32_t c = cp[i];
        if (c == '"' || c == '\\') {
            b->data[b->len++] = '\\'; b->data[b->len++] = (unsigned char)c;
        } else if (c == '\n') {
            b->data[b->len++] = '\\'; b->data[b->len++] = 'n';
        } else if (c == '\r') {
            b->data[b->len++] = '\\'; b->data[b->len++] = 'r';
        } else if (c == '\t') {
            b->data[b->len++] = '\\'; b->data[b->len++] = 't';
        } else if (c < 0x20) {
            char tmp[8];
            int k = snprintf(tmp, sizeof(tmp), "\\u%04x", c);
            memcpy(b->data + b->len, tmp, k);
            b->len += k;
        } else if (c < 0x80) {
            b->data[b->len++] = (unsigned char)c;
        } else if (c < 0x800) {
            b->data[b->len++] = 0xC0 | (c >> 6);
            b->data[b->len++] = 0x80 | (c & 0x3F);
        } else if (c < 0x10000) {
            b->data[b->len++] = 0xE0 | (c >> 12);
            b->data[b->len++] = 0x80 | ((c >> 6) & 0x3F);
            b->data[b->len++] = 0x80 | (c & 0x3F);
        } else {
            b->data[b->len++] = 0xF0 | (c >> 18);
            b->data[b->len++] = 0x80 | ((c >> 12) & 0x3F);
            b->data[b->len++] = 0x80 | ((c >> 6) & 0x3F);
            b->data[b->len++] = 0x80 | (c & 0x3F);
        }
    }
    b->data[b->len++] = '"';
}

// ---------------------------------------------------------------------
// Memory read primitives
// ---------------------------------------------------------------------
static bool read_mem_raw(uint64_t addr, void *out, size_t n) {
    if (!addr) return false;
    mach_vm_size_t got = 0;
    kern_return_t kr = mach_vm_read_overwrite(g_task, (mach_vm_address_t)addr,
                                               (mach_vm_size_t)n, (mach_vm_address_t)out, &got);
    return kr == KERN_SUCCESS && got == n;
}

// A walk is syscall-bound, not decode-bound: nearly every read is an 8-byte
// pointer field, and an object's header, its dict and that dict's entries all
// sit within a page or two of each other, so the same page is re-read dozens
// of times. Caching whole pages for the duration of one walk is what makes the
// difference; on a ~7,000-node live tree the walk goes 3.36s -> 0.39s, and a
// real mission run's reads went 1.81s -> 0.45s median, halving tick time.
//
// The cache is scoped to a single request on purpose. Holding it across reads
// would serve the bot a blend of pages fetched seconds apart, which is exactly
// the stale-tree failure the whole design avoids. Within one walk it is instead
// a small consistency gain, since the uncached walk already samples a live tree
// over several seconds.

// TW_-prefixed: <mach/mach.h> already defines PAGE_SIZE and PAGE_MASK.
#define TW_PAGE_BITS 12
#define TW_PAGE_SIZE (1u << TW_PAGE_BITS)
#define TW_PAGE_MASK (~(uint64_t)(TW_PAGE_SIZE - 1))
#define PAGE_CACHE_SLOTS 4096  // power of two; direct-mapped, ~16MB resident

typedef struct {
    uint64_t base;
    uint64_t epoch;
    bool usable;
    unsigned char data[TW_PAGE_SIZE];
} PageCacheEntry;

static PageCacheEntry *g_page_cache;
static uint64_t g_page_epoch = 1;

static bool read_mem(uint64_t addr, void *out, size_t n) {
    if (!addr) return false;
    // Ranges spanning two pages (only the fixed-size type-name and string
    // reads get near it) would need stitching for no real gain, and an
    // allocation failure leaves the cache disabled rather than the walker dead.
    if (!g_page_cache || n > TW_PAGE_SIZE) return read_mem_raw(addr, out, n);
    uint64_t base = addr & TW_PAGE_MASK;
    if (addr + n > base + TW_PAGE_SIZE) return read_mem_raw(addr, out, n);

    PageCacheEntry *e = &g_page_cache[(base >> TW_PAGE_BITS) & (PAGE_CACHE_SLOTS - 1)];
    if (e->epoch != g_page_epoch || e->base != base) {
        e->epoch = g_page_epoch;
        e->base = base;
        e->usable = read_mem_raw(base, e->data, TW_PAGE_SIZE);
    }
    // A page that cannot be read whole is not the same as an unreadable field:
    // the last page of a mapped region fails as a page while the bytes actually
    // asked for are fine. Falling back keeps those reads working.
    if (!e->usable) return read_mem_raw(addr, out, n);
    memcpy(out, e->data + (addr - base), n);
    return true;
}

static bool read_u64(uint64_t addr, uint64_t *out) {
    return read_mem(addr, out, 8);
}

// ---------------------------------------------------------------------
// Type classification (the ob_type-must-equal-the-'type'-metaclass
// invariant), with a small linear cache since a real walk only touches
// a handful of distinct classes repeatedly.
// ---------------------------------------------------------------------
#define TYPE_CACHE_MAX 256
typedef struct { uint64_t type_ptr; char name[128]; bool valid; } TypeCacheEntry;
static TypeCacheEntry g_type_cache[TYPE_CACHE_MAX];
static int g_type_cache_n = 0;

// Returns true and fills name (may be "") if type_ptr is a real
// PyTypeObject; false if not (NULL name untouched).
static bool type_name_if_valid(uint64_t type_ptr, char *name_out, size_t name_cap) {
    if (!type_ptr || (type_ptr & 0x7)) return false;
    for (int i = 0; i < g_type_cache_n; i++) {
        if (g_type_cache[i].type_ptr == type_ptr) {
            if (!g_type_cache[i].valid) return false;
            strncpy(name_out, g_type_cache[i].name, name_cap);
            return true;
        }
    }
    uint64_t ob_type = 0;
    bool valid = false;
    char name[128] = {0};
    if (read_u64(type_ptr + 8, &ob_type) && ob_type == g_metatype) {
        uint64_t tp_name_ptr = 0;
        if (read_u64(type_ptr + 0x18, &tp_name_ptr) && tp_name_ptr) {
            char raw[128] = {0};
            if (read_mem(tp_name_ptr, raw, sizeof(raw) - 1)) {
                strncpy(name, raw, sizeof(name) - 1);
                valid = true;
            }
        }
    }
    if (g_type_cache_n < TYPE_CACHE_MAX) {
        TypeCacheEntry *e = &g_type_cache[g_type_cache_n++];
        e->type_ptr = type_ptr;
        e->valid = valid;
        strncpy(e->name, name, sizeof(e->name) - 1);
    }
    if (!valid) return false;
    strncpy(name_out, name, name_cap);
    return true;
}

static bool get_type_name_of_obj(uint64_t obj_addr, char *name_out, size_t name_cap) {
    uint64_t type_ptr = 0;
    if (!read_u64(obj_addr + 8, &type_ptr)) return false;
    return type_name_if_valid(type_ptr, name_out, name_cap);
}

// obj_addr+0x10, if it's really a 'dict'-typed object
static bool get_dict(uint64_t obj_addr, uint64_t *dict_addr_out) {
    uint64_t dict_ptr = 0;
    if (!read_u64(obj_addr + 0x10, &dict_ptr) || !dict_ptr) return false;
    char name[128];
    if (!get_type_name_of_obj(dict_ptr, name, sizeof(name))) return false;
    if (strcmp(name, "dict") != 0) return false;
    *dict_addr_out = dict_ptr;
    return true;
}

// ---------------------------------------------------------------------
// Custom dict walk
// ---------------------------------------------------------------------
typedef struct { uint64_t hash, key_addr, value_addr; } DictEntry;
// walk_node (recursive) keeps arrays sized by this constant as LOCAL
// (stack) variables, once per call frame -- at the original 4096, that's
// ~396KB/frame (entries + keybuf[][64] + three bool/size_t arrays),
// which overflows the default 8MB thread stack around depth 20 and
// crashes with SIGSEGV (confirmed live: depth=18 fine, depth=20 crashed
// every time). The largest real dict seen anywhere in this project's
// memory-reading work is 139 attributes (OverviewWindow); 512 leaves
// generous headroom while cutting per-frame stack usage ~8x, enough for
// far deeper recursion than any real UI tree needs.
#define MAX_DICT_ENTRIES 512

// Fills out[] with every non-null (hash,key,value) triple from the
// inline block then the overflow block (in that order -- callers rely
// on this order for duplicate-key resolution). Returns count.
static int walk_dict_raw(uint64_t dict_addr, DictEntry *out, int max_out) {
    unsigned char header[0x38];
    if (!read_mem(dict_addr, header, sizeof(header))) return 0;
    int n = 0;

    unsigned char inline_block[8 * 24];
    if (read_mem(dict_addr + 0x38, inline_block, sizeof(inline_block))) {
        for (int i = 0; i < 8 && n < max_out; i++) {
            uint64_t h, k, v;
            memcpy(&h, inline_block + i * 24, 8);
            memcpy(&k, inline_block + i * 24 + 8, 8);
            memcpy(&v, inline_block + i * 24 + 16, 8);
            if (k) { out[n].hash = h; out[n].key_addr = k; out[n].value_addr = v; n++; }
        }
    }

    uint64_t overflow_ptr, mask;
    memcpy(&overflow_ptr, header + 0x28, 8);
    memcpy(&mask, header + 0x20, 8);
    uint64_t capacity = (mask && mask < (1u << 20)) ? mask + 1 : 0;
    if (overflow_ptr && capacity) {
        if (capacity > (uint64_t)(MAX_DICT_ENTRIES)) capacity = MAX_DICT_ENTRIES;
        unsigned char *overflow = malloc(capacity * 24);
        if (overflow && read_mem(overflow_ptr, overflow, capacity * 24)) {
            for (uint64_t i = 0; i < capacity && n < max_out; i++) {
                uint64_t h, k, v;
                memcpy(&h, overflow + i * 24, 8);
                memcpy(&k, overflow + i * 24 + 8, 8);
                memcpy(&v, overflow + i * 24 + 16, 8);
                if (k) { out[n].hash = h; out[n].key_addr = k; out[n].value_addr = v; n++; }
            }
        }
        free(overflow);
    }
    return n;
}

// ---------------------------------------------------------------------
// Primitive decoders
// ---------------------------------------------------------------------

// Compact-ASCII 'str': length @+0x10, ASCII bytes from @+0x24.
static bool decode_pystr(uint64_t addr, unsigned char *out, size_t out_cap, size_t *out_len) {
    uint64_t length = 0;
    if (!read_u64(addr + 0x10, &length)) return false;
    if (length > out_cap) length = out_cap;  // truncate defensively; real names are always short
    if (!read_mem(addr + 0x24, out, length)) return false;
    *out_len = length;
    return true;
}

static bool decode_pyint(uint64_t addr, int64_t *out) {
    return read_mem(addr + 0x10, out, 8);
}

static bool decode_pyfloat(uint64_t addr, double *out) {
    return read_mem(addr + 0x10, out, 8);
}

// Python-2-style PyLongObject: signed ob_size (digit count + sign) at
// +0x10, then that many 30-bit digits (4 bytes each) from +0x18.
static bool decode_pylong(uint64_t addr, double *out_as_double, int64_t *out_as_int, bool *is_exact_int) {
    int64_t ob_size;
    if (!read_mem(addr + 0x10, &ob_size, 8)) return false;
    if (ob_size == 0) { *out_as_int = 0; *is_exact_int = true; return true; }
    int64_t ndigits = ob_size < 0 ? -ob_size : ob_size;
    if (ndigits > 64) return false;
    uint32_t digits[64];
    if (!read_mem(addr + 0x18, digits, ndigits * 4)) return false;

    // Real values seen in practice (timestamps etc) run up to ~60 bits,
    // well past a double's 53-bit exact-integer range -- accumulating in
    // double lost precision (off by a handful of units on real 2-digit
    // longs, caught by diffing against the proven Python implementation
    // before trusting this). __int128 covers up to 4 digits (120 bits)
    // exactly; only genuinely bigger bignums fall back to double (lossy,
    // but rare -- JSON/IEEE-754 has no exact-bignum representation
    // anyway, matching what the JSON wire format can even carry).
    if (ndigits <= 4) {
        __int128 value = 0;
        __int128 scale = 1;
        for (int64_t i = 0; i < ndigits; i++) {
            value += (__int128)digits[i] * scale;
            scale *= (__int128)1 << 30;
        }
        if (ob_size < 0) value = -value;
        if (value >= INT64_MIN && value <= INT64_MAX) {
            *out_as_int = (int64_t)value;
            *is_exact_int = true;
            *out_as_double = (double)value;
            return true;
        }
        *out_as_double = (double)value;
        *is_exact_int = false;
        return true;
    }

    double value = 0.0;
    double scale = 1.0;
    for (int64_t i = 0; i < ndigits; i++) {
        value += digits[i] * scale;
        scale *= (double)(1 << 30);
    }
    if (ob_size < 0) value = -value;
    *out_as_double = value;
    *is_exact_int = false;
    return true;
}

// Python-2-style PyUnicodeObject: length @+0x10, external UCS-4 buffer
// pointer @+0x18.
static bool decode_pyunicode(uint64_t addr, Buf *out) {
    uint64_t length = 0, buf_ptr = 0;
    if (!read_u64(addr + 0x10, &length)) return false;
    if (!read_u64(addr + 0x18, &buf_ptr)) return false;
    if (length > 8192) return false;
    uint32_t *cps = malloc(length * 4);
    if (!cps) return false;
    bool ok = length == 0 || read_mem(buf_ptr, cps, length * 4);
    if (ok) buf_json_escape_utf32(out, cps, length);
    free(cps);
    return ok;
}

// Forward declaration: describe_link_json (below) recurses into this to
// decode its `_text` value (a str or unicode), and this dispatches to
// describe_link_json for Link-typed values -- mutual reference.
static bool describe_primitive_json(uint64_t value_addr, Buf *out);

// Link: a rich-text hyperlink object (e.g. a solar-system-name label's
// `_setText`), matching the exact gap this project's own Elm decoder
// comment has documented for years: "_setText contained not string but
// a python object of type Link, which in turn references a dictionary.
// That dictionary contains a key _text with the actual text." Unlike
// PyColor, Link's own dict pointer is NOT at the usual +0x10 (that slot
// holds an unrelated small int/handle); tp_basicsize is 64 bytes (double
// the standard 32-byte wrapper) and the real dict sits at +0x30 --
// confirmed live by dumping a whole instance and testing each word
// against the type-metaclass invariant (see re_helper.py's decode_link,
// matching this field-for-field). Returns false if no `_text` key is
// found (never guess a string).
static bool describe_link_json(uint64_t addr, Buf *out) {
    uint64_t dict_addr = 0;
    if (!read_u64(addr + 0x30, &dict_addr) || !dict_addr) return false;
    char tname[128];
    if (!get_type_name_of_obj(dict_addr, tname, sizeof(tname)) || strcmp(tname, "dict") != 0) return false;

    DictEntry entries[64];
    int n = walk_dict_raw(dict_addr, entries, 64);
    for (int i = 0; i < n; i++) {
        unsigned char keybuf[16];
        size_t klen;
        if (!decode_pystr(entries[i].key_addr, keybuf, sizeof(keybuf), &klen)) continue;
        if (klen == 5 && memcmp(keybuf, "_text", 5) == 0 && entries[i].value_addr) {
            return describe_primitive_json(entries[i].value_addr, out);
        }
    }
    return false;
}

// PyColor: an ordinary widget-shaped object (dict at +0x10) whose own
// __dict__ holds `_r`/`_g`/`_b`/`_a` floats in [0, 1]. Overview-entry
// hostility detection (iconSpriteHasColorOfRat in the EVE bots) reads
// this via a `_color` attribute decoded as {aPercent, rPercent,
// gPercent, bPercent} -- confirmed live against a real NPC overview
// icon's `_color` value (see re_helper.py's decode_pycolor, matching
// this one field-for-field) before trusting this shape. Appends nothing
// and returns false if the expected fields aren't all present (never
// guess a color).
static bool describe_pycolor_json(uint64_t addr, Buf *out) {
    uint64_t dict_addr;
    if (!get_dict(addr, &dict_addr)) return false;

    DictEntry entries[64];
    int n = walk_dict_raw(dict_addr, entries, 64);

    bool have_r = false, have_g = false, have_b = false, have_a = false;
    double r = 0, g = 0, b = 0, a = 0;
    for (int i = 0; i < n; i++) {
        unsigned char keybuf[16];
        size_t klen;
        if (!decode_pystr(entries[i].key_addr, keybuf, sizeof(keybuf), &klen) || klen != 2) continue;
        double v;
        if (!decode_pyfloat(entries[i].value_addr, &v)) continue;
        if (keybuf[0] != '_') continue;
        if (keybuf[1] == 'r' && !have_r) { r = v; have_r = true; }
        else if (keybuf[1] == 'g' && !have_g) { g = v; have_g = true; }
        else if (keybuf[1] == 'b' && !have_b) { b = v; have_b = true; }
        else if (keybuf[1] == 'a' && !have_a) { a = v; have_a = true; }
    }
    if (!(have_r && have_g && have_b && have_a)) return false;

    char tmp[128];
    int k = snprintf(tmp, sizeof(tmp),
                      "{\"aPercent\":%lld,\"rPercent\":%lld,\"gPercent\":%lld,\"bPercent\":%lld}",
                      (long long)lround(a * 100), (long long)lround(r * 100),
                      (long long)lround(g * 100), (long long)lround(b * 100));
    buf_append(out, tmp, k);
    return true;
}

// Appends a JSON value for `value_addr` if it's one of the recognized
// scalar kinds; returns false (appends nothing) for nested
// objects/containers, matching describe_primitive's scope in the Python
// implementation.
// A JSON number is a double by the time anything downstream sees it (the bot
// host parses this with JSON.parse before Elm decodes it), so an integer past
// 2^53 silently loses its low digits in transit. That is not hypothetical:
// EVE's object ids are ~9e18, and on one real grid 18 distinct overview
// itemIDs collapsed to 5 distinct doubles -- enough to make two different
// wrecks look like the same object. Emit those as JSON strings so the digits
// survive; ParseUserInterface already decodes ids with an int-or-string
// decoder. Values inside the safe range keep their old numeric form, so
// nothing that worked before changes shape.
#define JSON_MAX_EXACT_INTEGER 9007199254740992LL  // 2^53

static void emit_integer_json(Buf *out, int64_t v) {
    char tmp[32];
    int k = snprintf(tmp, sizeof(tmp), "%lld", (long long)v);
    if (v > JSON_MAX_EXACT_INTEGER || v < -JSON_MAX_EXACT_INTEGER) {
        buf_str(out, "\"");
        buf_append(out, tmp, k);
        buf_str(out, "\"");
    } else {
        buf_append(out, tmp, k);
    }
}

static bool describe_primitive_json(uint64_t value_addr, Buf *out) {
    if (!value_addr) return false;
    char tname[128];
    if (!get_type_name_of_obj(value_addr, tname, sizeof(tname))) return false;

    if (strcmp(tname, "str") == 0) {
        unsigned char tmp[4096];
        size_t n;
        if (!decode_pystr(value_addr, tmp, sizeof(tmp), &n)) return false;
        buf_json_escape(out, tmp, n);
        return true;
    }
    if (strcmp(tname, "float") == 0) {
        double v;
        if (!decode_pyfloat(value_addr, &v)) return false;
        char tmp[64];
        int k = snprintf(tmp, sizeof(tmp), "%.17g", v);
        buf_append(out, tmp, k);
        return true;
    }
    if (strcmp(tname, "bool") == 0) {
        int64_t v;
        if (!decode_pyint(value_addr, &v)) return false;
        buf_str(out, v ? "true" : "false");
        return true;
    }
    if (strcmp(tname, "int") == 0) {
        int64_t v;
        if (!decode_pyint(value_addr, &v)) return false;
        emit_integer_json(out, v);
        return true;
    }
    if (strcmp(tname, "long") == 0) {
        double dv; int64_t iv; bool exact;
        if (!decode_pylong(value_addr, &dv, &iv, &exact)) return false;
        if (exact) {
            emit_integer_json(out, iv);
        } else {
            char tmp[64];
            int k = snprintf(tmp, sizeof(tmp), "%.17g", dv);
            buf_append(out, tmp, k);
        }
        return true;
    }
    if (strcmp(tname, "unicode") == 0) {
        return decode_pyunicode(value_addr, out);
    }
    if (strcmp(tname, "PyColor") == 0) {
        return describe_pycolor_json(value_addr, out);
    }
    if (strcmp(tname, "Link") == 0) {
        return describe_link_json(value_addr, out);
    }
    // NoneType and anything else (nested instances/containers): omit,
    // matching the Python implementation.
    return false;
}

// ---------------------------------------------------------------------
// Children resolution: obj.__dict__['children'] (a PyChildrenList) ->
// its own __dict__['_childrenObjects'] -> stock CPython list -> ob_item
// array of child pointers.
//
// Some widgets nest one children-list wrapper inside another, so
// '_childrenObjects' is not always the stock list directly: a ButtonGroup
// (the row of Accept/Decline/... buttons in an agent conversation) goes
// ButtonGroup.children -> ButtonGroupChildrenList._childrenObjects ->
// PyChildrenList._childrenObjects -> list. Bailing out at the first
// non-list made every such subtree read as having no children at all,
// which is why an agent dialogue's buttons were invisible to the walk
// while plainly rendered on screen. Unwrap repeatedly instead, with a
// small bound so a corrupt or cyclic chain can't spin.
// ---------------------------------------------------------------------
#define MAX_CHILDREN_UNWRAP 4

static bool find_children_objects(uint64_t wrapper, uint64_t *out_value) {
    uint64_t wrapper_dict;
    if (!get_dict(wrapper, &wrapper_dict)) return false;
    DictEntry entries[64];
    int n = walk_dict_raw(wrapper_dict, entries, 64);
    // first-occurrence-wins, matching the Python implementation
    for (int i = 0; i < n; i++) {
        unsigned char keybuf[64];
        size_t klen;
        if (decode_pystr(entries[i].key_addr, keybuf, sizeof(keybuf), &klen) &&
            klen == 16 && memcmp(keybuf, "_childrenObjects", 16) == 0) {
            *out_value = entries[i].value_addr;
            return true;
        }
    }
    return false;
}

static int get_children_addrs(uint64_t children_wrapper, uint64_t *out, int max_out) {
    if (!children_wrapper) return 0;

    uint64_t child_objs_list = children_wrapper;
    char tname[128];
    for (int hop = 0; ; hop++) {
        if (!find_children_objects(child_objs_list, &child_objs_list)) return 0;
        if (!child_objs_list) return 0;
        if (!get_type_name_of_obj(child_objs_list, tname, sizeof(tname))) return 0;
        if (strcmp(tname, "list") == 0) break;
        if (hop + 1 >= MAX_CHILDREN_UNWRAP) return 0;
    }

    unsigned char hdr[40];
    if (!read_mem(child_objs_list, hdr, sizeof(hdr))) return 0;
    uint64_t ob_size, ob_item;
    memcpy(&ob_size, hdr + 0x10, 8);
    memcpy(&ob_item, hdr + 0x18, 8);
    if (ob_size > (uint64_t)max_out) ob_size = max_out;
    if (ob_size == 0) return 0;
    if (!read_mem(ob_item, out, ob_size * 8)) return 0;
    return (int)ob_size;
}

// ---------------------------------------------------------------------
// The recursive tree walk itself
// ---------------------------------------------------------------------
static int g_node_budget;

static void walk_node(uint64_t obj_addr, int depth, int max_depth, Buf *out) {
    g_node_budget--;
    char tname[128];
    bool have_type = get_type_name_of_obj(obj_addr, tname, sizeof(tname));

    char addr_hex[24];
    snprintf(addr_hex, sizeof(addr_hex), "0x%llx", (unsigned long long)obj_addr);

    buf_str(out, "{\"pythonObjectAddress\":");
    buf_json_escape(out, (unsigned char *)addr_hex, strlen(addr_hex));
    buf_str(out, ",\"pythonObjectTypeName\":");
    if (have_type) buf_json_escape(out, (unsigned char *)tname, strlen(tname));
    else buf_str(out, "null");
    buf_str(out, ",\"dictEntriesOfInterest\":{");

    uint64_t dict_addr = 0;
    uint64_t children_wrapper = 0;
    bool first_attr = true;

    if (get_dict(obj_addr, &dict_addr)) {
        DictEntry entries[MAX_DICT_ENTRIES];
        int n = walk_dict_raw(dict_addr, entries, MAX_DICT_ENTRIES);

        // Decode each entry's key once; build the deduped
        // (last-attr-wins, first-children-wins) view exactly like the
        // Python implementation. With n capped at a few hundred, an
        // O(n^2) dedupe by decoded key content is negligible cost.
        unsigned char keybuf[MAX_DICT_ENTRIES][64];
        size_t keylen[MAX_DICT_ENTRIES];
        bool key_ok[MAX_DICT_ENTRIES];
        for (int i = 0; i < n; i++) {
            key_ok[i] = decode_pystr(entries[i].key_addr, keybuf[i], sizeof(keybuf[i]), &keylen[i]);
        }

        bool is_children_key[MAX_DICT_ENTRIES];
        for (int i = 0; i < n; i++) {
            is_children_key[i] = key_ok[i] && keylen[i] == 8 && memcmp(keybuf[i], "children", 8) == 0;
            if (is_children_key[i] && !children_wrapper) children_wrapper = entries[i].value_addr;
        }

        bool suppressed[MAX_DICT_ENTRIES] = {0};  // an earlier dup of this key already emitted (we keep the LAST, so suppress earlier ones)
        for (int i = 0; i < n; i++) {
            if (!key_ok[i] || is_children_key[i] || suppressed[i] || !entries[i].value_addr) continue;
            for (int j = i + 1; j < n; j++) {
                if (key_ok[j] && !is_children_key[j] && keylen[j] == keylen[i] &&
                    memcmp(keybuf[j], keybuf[i], keylen[i]) == 0) {
                    suppressed[i] = true;  // a later occurrence exists -> this one loses
                    break;
                }
            }
            if (suppressed[i]) continue;

            size_t before = out->len;
            if (!first_attr) buf_str(out, ",");
            buf_json_escape(out, keybuf[i], keylen[i]);
            buf_str(out, ":");
            size_t value_start = out->len;
            if (!describe_primitive_json(entries[i].value_addr, out)) {
                out->len = before;  // no primitive value: roll back (including the comma/key we just wrote)
                continue;
            }
            (void)value_start;
            first_attr = false;
        }
    }
    buf_str(out, "},\"children\":[");

    if (depth < max_depth && g_node_budget > 0 && children_wrapper) {
        uint64_t child_addrs[1024];
        int nchildren = get_children_addrs(children_wrapper, child_addrs, 1024);
        bool first_child = true;
        for (int i = 0; i < nchildren && g_node_budget > 0; i++) {
            if (!child_addrs[i]) continue;
            if (!first_child) buf_str(out, ",");
            walk_node(child_addrs[i], depth + 1, max_depth, out);
            first_child = false;
        }
    }
    buf_str(out, "]}");
}

// ---------------------------------------------------------------------
// Main: persistent process, one request per line (binary framing)
// ---------------------------------------------------------------------
static int read_full(int fd, void *buf, size_t n) {
    size_t got = 0;
    while (got < n) {
        ssize_t r = read(fd, (char *)buf + got, n - got);
        if (r <= 0) return -1;
        got += (size_t)r;
    }
    return 0;
}

static int write_full(int fd, const void *buf, size_t n) {
    size_t sent = 0;
    while (sent < n) {
        ssize_t w = write(fd, (const char *)buf + sent, n - sent);
        if (w <= 0) return -1;
        sent += (size_t)w;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <pid>\n", argv[0]);
        return 1;
    }
    pid_t pid = atoi(argv[1]);

    kern_return_t kr = task_for_pid(mach_task_self(), pid, &g_task);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "task_for_pid failed: %s (kr=%d)\n", mach_error_string(kr), kr);
        return 1;
    }
    g_page_cache = calloc(PAGE_CACHE_SLOTS, sizeof(PageCacheEntry));

    fprintf(stderr, "ready\n");
    fflush(stderr);

    unsigned char req[32];
    while (read_full(0, req, sizeof(req)) == 0) {
        uint64_t root_addr, metatype_addr, str_type_addr;
        uint32_t max_depth, max_nodes;
        memcpy(&root_addr, req, 8);
        memcpy(&metatype_addr, req + 8, 8);
        memcpy(&str_type_addr, req + 16, 8);
        memcpy(&max_depth, req + 24, 4);
        memcpy(&max_nodes, req + 28, 4);
        (void)str_type_addr;  // not needed: type classification only needs the metatype invariant

        g_metatype = metatype_addr;
        g_type_cache_n = 0;  // types are process-run-scoped, but keep it simple: fresh cache per request
        g_page_epoch++;      // invalidates every cached page without touching them
        g_node_budget = (int)max_nodes;

        Buf out;
        buf_init(&out);
        walk_node(root_addr, 0, (int)max_depth, &out);

        uint64_t len64 = out.len;
        if (write_full(1, &len64, 8) != 0) break;
        if (write_full(1, out.data, out.len) != 0) break;
        free(out.data);
    }
    return 0;
}
