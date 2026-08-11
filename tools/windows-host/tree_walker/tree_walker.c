// The UI-tree walk in C, for Windows. The port of
// tools/macos-host/tree_walker/tree_walker.c, which is where every rule below
// comes from and where the reasons for them are written down at length.
//
// WHY THIS EXISTS, given the Python walker in ../tree_walker.py already works.
//
// It is not the memory reads. Measured on this client, a 4 KiB
// ReadProcessMemory costs 9.6us and an 8-byte one 5.2us, so the ~10,000 reads a
// walk makes are 0.10s of it. The Python walker's remaining ~1.3s is CPython
// interpreter overhead: 1,163,675 read calls for 3,617 nodes before memoising,
// and ~370,000 after. That is the same place the macOS project stood before it
// wrote its own C walker -- "genuinely CPU-bound on CPython interpreter
// overhead (millions of small operations for one tree read) once round-trip
// count and data volume were no longer the bottleneck".
//
// And on Windows the cost is not only throughput. ShipUI.hitpointsPercent is
// read out of a widget the client is mutating, and a garbage value is "a read
// landing on a reallocated object". Over one saxrat run 143 of 893 gauge
// readings were implausible and they arrived in runs, which defeats the Elm
// side's `believed` filter (built to absorb one bad reading, not consecutive
// ones) and fired the retreat 229 times on a hull at full armour. A shorter
// walk leaves less of the tree reallocated underneath it.
//
// WHAT DIFFERS FROM THE macOS FILE, all of it measured by ../probe.py:
//   - mach_vm_read_overwrite            -> ReadProcessMemory
//   - a str's characters at +0x24       -> +0x20   (Windows x64 is LLP64, so
//   - PyIntObject.ob_ival is 8 bytes    -> 4 bytes  sizeof(long) is 4 not 8)
//   - unicode is UCS-4                  -> UCS-2   (a build option, not an ABI
//                                                   consequence; wchar_t here)
//   - the metatype is discovered by scan -> passed in, since python27.dll
//                                           exports PyType_Type
// Everything else -- the object header, PyTypeObject, Blue's custom dict, the
// stock list, the walk, the ordering rules -- is byte-identical to macOS.
//
// Protocol, unchanged from the macOS binary so botlab_host.py's TreeWalkerClient
// works against either without knowing which it has:
//   stdin :  <root u64><metatype u64><str_type u64><max_depth u32><max_nodes u32>
//   stdout:  <length u64><length bytes of UTF-8 JSON>
//   stderr:  "ready\n" once attached.
//
// Build: build.bat  (or see it for the one cl.exe line).

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <math.h>
#include <io.h>
#include <fcntl.h>

// ---------------------------------------------------------------------
// Struct layout for this build. See the header comment for which of these
// differ from macOS and why.
// ---------------------------------------------------------------------
#define OFF_OB_TYPE        0x08
#define OFF_OB_SIZE        0x10
#define OFF_TP_NAME        0x18
#define OFF_STR_CHARS      0x20   // macOS: 0x24
#define OFF_INT_VALUE      0x10   // read as int32 here, int64 on macOS
#define OFF_LONG_DIGITS    0x18
#define OFF_UNICODE_LEN    0x10
#define OFF_UNICODE_BUF    0x18
#define OFF_FLOAT_VALUE    0x10
#define OFF_LIST_ITEMS     0x18
#define OFF_WIDGET_DICT    0x10
#define DICT_HEADER        0x38
#define DICT_MASK          0x20
#define DICT_OVERFLOW      0x28
#define DICT_ENTRY_SIZE    0x18
#define DICT_INLINE        8
#define OFF_LINK_DICT      0x30

static HANDLE g_process = NULL;
static uint64_t g_metatype = 0;
static uint64_t g_str_type = 0;

// ---------------------------------------------------------------------
// Output buffer
// ---------------------------------------------------------------------
typedef struct { char *p; size_t len, cap; } Buf;

static void buf_init(Buf *b) { b->cap = 1 << 20; b->p = (char *)malloc(b->cap); b->len = 0; }

static void buf_ensure(Buf *b, size_t extra) {
    if (b->len + extra <= b->cap) return;
    while (b->len + extra > b->cap) b->cap *= 2;
    b->p = (char *)realloc(b->p, b->cap);
}

static void buf_append(Buf *b, const void *p, size_t n) {
    buf_ensure(b, n);
    memcpy(b->p + b->len, p, n);
    b->len += n;
}

static void buf_str(Buf *b, const char *s) { buf_append(b, s, strlen(s)); }

// A JSON string from raw bytes. Bytes above 0x7F are emitted as-is: the client's
// str values are effectively UTF-8 and re-encoding them would be a second guess
// about an encoding this program has no better information about than the
// consumer does.
static void buf_json_escape(Buf *b, const unsigned char *s, size_t n) {
    buf_str(b, "\"");
    for (size_t i = 0; i < n; i++) {
        unsigned char c = s[i];
        switch (c) {
            case '"':  buf_str(b, "\\\""); break;
            case '\\': buf_str(b, "\\\\"); break;
            case '\n': buf_str(b, "\\n"); break;
            case '\r': buf_str(b, "\\r"); break;
            case '\t': buf_str(b, "\\t"); break;
            default:
                if (c < 0x20) {
                    char tmp[8];
                    snprintf(tmp, sizeof(tmp), "\\u%04x", c);
                    buf_str(b, tmp);
                } else {
                    buf_append(b, &c, 1);
                }
        }
    }
    buf_str(b, "\"");
}

// A JSON string from a UCS-2 buffer. The macOS file has the UCS-4 twin of this.
// Surrogate halves are passed through as \uXXXX rather than refused, because a
// lone surrogate is legal in a Python 2 UCS-2 buffer and dropping the whole
// string over one would be the silent loss this port already paid for once.
static void buf_json_escape_ucs2(Buf *b, const uint16_t *cp, size_t n) {
    buf_str(b, "\"");
    for (size_t i = 0; i < n; i++) {
        uint16_t c = cp[i];
        switch (c) {
            case '"':  buf_str(b, "\\\""); break;
            case '\\': buf_str(b, "\\\\"); break;
            case '\n': buf_str(b, "\\n"); break;
            case '\r': buf_str(b, "\\r"); break;
            case '\t': buf_str(b, "\\t"); break;
            default:
                if (c < 0x20 || c > 0x7E) {
                    char tmp[8];
                    snprintf(tmp, sizeof(tmp), "\\u%04x", c);
                    buf_str(b, tmp);
                } else {
                    char ch = (char)c;
                    buf_append(b, &ch, 1);
                }
        }
    }
    buf_str(b, "\"");
}

// ---------------------------------------------------------------------
// Memory reading, with the same per-request page cache the macOS file has and
// for the same two reasons: an object's header, its dict and that dict's
// entries sit within a page or two of each other, and holding pages across
// requests would hand the bot a tree blended from moments seconds apart.
// ---------------------------------------------------------------------
#define TW_PAGE_BITS 12
#define TW_PAGE_SIZE (1u << TW_PAGE_BITS)
#define TW_PAGE_MASK (~(uint64_t)(TW_PAGE_SIZE - 1))
#define PAGE_CACHE_SLOTS 8192  // power of two; direct-mapped, ~32MB resident

typedef struct {
    uint64_t tag;      // page base, 0 = empty
    uint32_t epoch;
    bool ok;
    unsigned char data[TW_PAGE_SIZE];
} PageSlot;

static PageSlot *g_pages = NULL;
static uint32_t g_page_epoch = 1;
static uint64_t g_reads = 0;

static bool read_mem_raw(uint64_t addr, void *out, size_t n) {
    SIZE_T got = 0;
    g_reads++;
    if (!ReadProcessMemory(g_process, (LPCVOID)(uintptr_t)addr, out, n, &got)) return false;
    return got == n;
}

static bool read_mem(uint64_t addr, void *out, size_t n) {
    if (!addr) return false;
    uint64_t first = addr & TW_PAGE_MASK;
    uint64_t last = (addr + n - 1) & TW_PAGE_MASK;
    if (first != last) {
        // Spans pages; rare for the small fields this reads, so take it direct
        // rather than stitching.
        return read_mem_raw(addr, out, n);
    }
    size_t slot = (size_t)((first >> TW_PAGE_BITS) & (PAGE_CACHE_SLOTS - 1));
    PageSlot *p = &g_pages[slot];
    if (p->tag != first || p->epoch != g_page_epoch) {
        if (!read_mem_raw(first, p->data, TW_PAGE_SIZE)) {
            // The last page of a mapped region fails as a page while the bytes
            // asked for are fine. Fall back rather than reporting the field
            // unreadable -- macOS hit this too.
            p->tag = 0;
            return read_mem_raw(addr, out, n);
        }
        p->tag = first;
        p->epoch = g_page_epoch;
        p->ok = true;
    }
    memcpy(out, p->data + (addr - first), n);
    return true;
}

static bool read_u64(uint64_t addr, uint64_t *out) { return read_mem(addr, out, 8); }

// ---------------------------------------------------------------------
// Type names. The metatype is handed to us rather than discovered, since
// python27.dll exports PyType_Type; the validity rule is otherwise macOS's.
// ---------------------------------------------------------------------
#define TYPE_CACHE_MAX 512
typedef struct { uint64_t type_ptr; char name[128]; bool valid; } TypeCacheEntry;
static TypeCacheEntry g_type_cache[TYPE_CACHE_MAX];
static int g_type_cache_n = 0;

static bool type_name_if_valid(uint64_t type_ptr, char *name_out, size_t name_cap) {
    if (!type_ptr || (type_ptr & 0x7)) return false;
    for (int i = 0; i < g_type_cache_n; i++) {
        if (g_type_cache[i].type_ptr == type_ptr) {
            if (!g_type_cache[i].valid) return false;
            strncpy(name_out, g_type_cache[i].name, name_cap - 1);
            name_out[name_cap - 1] = '\0';
            return true;
        }
    }
    uint64_t ob_type = 0;
    bool valid = false;
    char name[128] = {0};
    if (read_u64(type_ptr + OFF_OB_TYPE, &ob_type) && ob_type == g_metatype) {
        uint64_t tp_name_ptr = 0;
        if (read_u64(type_ptr + OFF_TP_NAME, &tp_name_ptr) && tp_name_ptr) {
            char raw[128] = {0};
            if (read_mem(tp_name_ptr, raw, sizeof(raw) - 1)) {
                raw[sizeof(raw) - 1] = '\0';
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
    strncpy(name_out, name, name_cap - 1);
    name_out[name_cap - 1] = '\0';
    return true;
}

static bool get_type_name_of_obj(uint64_t obj_addr, char *name_out, size_t name_cap) {
    uint64_t type_ptr = 0;
    if (!read_u64(obj_addr + OFF_OB_TYPE, &type_ptr)) return false;
    return type_name_if_valid(type_ptr, name_out, name_cap);
}

static bool get_dict(uint64_t obj_addr, uint64_t *dict_addr_out) {
    uint64_t dict_ptr = 0;
    if (!read_u64(obj_addr + OFF_WIDGET_DICT, &dict_ptr) || !dict_ptr) return false;
    char name[128];
    if (!get_type_name_of_obj(dict_ptr, name, sizeof(name))) return false;
    if (strcmp(name, "dict") != 0) return false;
    *dict_addr_out = dict_ptr;
    return true;
}

// ---------------------------------------------------------------------
// Blue's custom dict
// ---------------------------------------------------------------------
typedef struct { uint64_t hash, key_addr, value_addr; } DictEntry;
#define MAX_DICT_ENTRIES 512

// Inline block then overflow, in that order -- callers resolve duplicate keys
// by position, so the order is part of the contract.
static int walk_dict_raw(uint64_t dict_addr, DictEntry *out, int max_out) {
    unsigned char header[DICT_HEADER];
    if (!read_mem(dict_addr, header, sizeof(header))) return 0;
    int n = 0;

    unsigned char inline_block[DICT_INLINE * DICT_ENTRY_SIZE];
    if (read_mem(dict_addr + DICT_HEADER, inline_block, sizeof(inline_block))) {
        for (int i = 0; i < DICT_INLINE && n < max_out; i++) {
            uint64_t h, k, v;
            memcpy(&h, inline_block + i * DICT_ENTRY_SIZE, 8);
            memcpy(&k, inline_block + i * DICT_ENTRY_SIZE + 8, 8);
            memcpy(&v, inline_block + i * DICT_ENTRY_SIZE + 16, 8);
            if (k) { out[n].hash = h; out[n].key_addr = k; out[n].value_addr = v; n++; }
        }
    }

    uint64_t overflow_ptr, mask;
    memcpy(&overflow_ptr, header + DICT_OVERFLOW, 8);
    memcpy(&mask, header + DICT_MASK, 8);
    uint64_t capacity = (mask && mask < (1u << 20)) ? mask + 1 : 0;
    if (overflow_ptr && capacity) {
        if (capacity > (uint64_t)MAX_DICT_ENTRIES) capacity = MAX_DICT_ENTRIES;
        unsigned char *overflow = (unsigned char *)malloc((size_t)capacity * DICT_ENTRY_SIZE);
        if (overflow && read_mem(overflow_ptr, overflow, (size_t)capacity * DICT_ENTRY_SIZE)) {
            for (uint64_t i = 0; i < capacity && n < max_out; i++) {
                uint64_t h, k, v;
                memcpy(&h, overflow + i * DICT_ENTRY_SIZE, 8);
                memcpy(&k, overflow + i * DICT_ENTRY_SIZE + 8, 8);
                memcpy(&v, overflow + i * DICT_ENTRY_SIZE + 16, 8);
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
static bool decode_pystr(uint64_t addr, unsigned char *out, size_t out_cap, size_t *out_len) {
    uint64_t length = 0;
    if (!read_u64(addr + OFF_OB_SIZE, &length)) return false;
    if (length > out_cap) length = out_cap;
    if (!read_mem(addr + OFF_STR_CHARS, out, (size_t)length)) return false;
    *out_len = (size_t)length;
    return true;
}

// 4 bytes here, 8 on macOS: PyIntObject.ob_ival is a bare `long`.
static bool decode_pyint(uint64_t addr, int64_t *out) {
    int32_t v = 0;
    if (!read_mem(addr + OFF_INT_VALUE, &v, 4)) return false;
    *out = (int64_t)v;
    return true;
}

static bool decode_pyfloat(uint64_t addr, double *out) {
    return read_mem(addr + OFF_FLOAT_VALUE, out, 8);
}

// ob_size is the digit count and sign; digits are 30-bit and 4 bytes each.
// Accumulated exactly where it fits in an int64, because real in-game
// timestamps exceed what a double holds without loss.
static bool decode_pylong(uint64_t addr, double *out_as_double, int64_t *out_as_int, bool *is_exact_int) {
    int64_t ob_size = 0;
    if (!read_mem(addr + OFF_OB_SIZE, &ob_size, 8)) return false;
    int64_t count = ob_size < 0 ? -ob_size : ob_size;
    if (count > 64) return false;
    if (count == 0) { *out_as_double = 0; *out_as_int = 0; *is_exact_int = true; return true; }
    uint32_t digits[64];
    if (!read_mem(addr + OFF_LONG_DIGITS, digits, (size_t)count * 4)) return false;

    double acc_d = 0;
    unsigned __int64 acc_u = 0;
    bool exact = true;
    for (int64_t i = count - 1; i >= 0; i--) {
        if (digits[i] >= (1u << 30)) return false;
        acc_d = acc_d * (double)(1u << 30) + (double)digits[i];
        if (exact) {
            if (acc_u > (~0ULL >> 30)) exact = false;
            else acc_u = (acc_u << 30) | digits[i];
        }
    }
    if (acc_u > (unsigned __int64)INT64_MAX) exact = false;
    *out_as_double = ob_size < 0 ? -acc_d : acc_d;
    *out_as_int = ob_size < 0 ? -(int64_t)acc_u : (int64_t)acc_u;
    *is_exact_int = exact;
    return true;
}

// UCS-2 here, UCS-4 on macOS.
static bool decode_pyunicode(uint64_t addr, Buf *out) {
    uint64_t length = 0, buffer = 0;
    if (!read_u64(addr + OFF_UNICODE_LEN, &length)) return false;
    if (!read_u64(addr + OFF_UNICODE_BUF, &buffer) || !buffer) return false;
    if (length > 4096) length = 4096;
    if (length == 0) { buf_str(out, "\"\""); return true; }
    uint16_t *tmp = (uint16_t *)malloc((size_t)length * 2);
    if (!tmp) return false;
    if (!read_mem(buffer, tmp, (size_t)length * 2)) { free(tmp); return false; }
    buf_json_escape_ucs2(out, tmp, (size_t)length);
    free(tmp);
    return true;
}

static bool describe_primitive_json(uint64_t value_addr, Buf *out);

// Link: a rich-text hyperlink whose own dict is NOT at the usual +0x10 (that
// slot holds an unrelated handle); tp_basicsize is 64 and the dict sits at
// +0x30. Returns false if there is no `_text` -- never guess a string.
static bool describe_link_json(uint64_t addr, Buf *out) {
    uint64_t dict_addr = 0;
    if (!read_u64(addr + OFF_LINK_DICT, &dict_addr) || !dict_addr) return false;
    char tname[128];
    if (!get_type_name_of_obj(dict_addr, tname, sizeof(tname)) || strcmp(tname, "dict") != 0) return false;
    DictEntry entries[64];
    int n = walk_dict_raw(dict_addr, entries, 64);
    for (int i = 0; i < n; i++) {
        unsigned char keybuf[16];
        size_t klen;
        if (!decode_pystr(entries[i].key_addr, keybuf, sizeof(keybuf), &klen)) continue;
        if (klen == 5 && memcmp(keybuf, "_text", 5) == 0 && entries[i].value_addr)
            return describe_primitive_json(entries[i].value_addr, out);
    }
    return false;
}

// PyColor: a widget-shaped object whose dict holds _r/_g/_b/_a floats in [0,1].
// Appends nothing and returns false unless all four are present.
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
                     (long long)llround(a * 100), (long long)llround(r * 100),
                     (long long)llround(g * 100), (long long)llround(b * 100));
    buf_append(out, tmp, k);
    return true;
}

// A JSON number is a double by the time Elm sees it and EVE's object ids are
// ~9e18, so anything past 2^53 goes out as a string -- on one real grid 18
// distinct overview itemIDs collapsed to 5 distinct doubles without this.
#define JSON_MAX_EXACT_INTEGER 9007199254740992LL

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
        if (exact) emit_integer_json(out, iv);
        else {
            char tmp[64];
            int k = snprintf(tmp, sizeof(tmp), "%.17g", dv);
            buf_append(out, tmp, k);
        }
        return true;
    }
    if (strcmp(tname, "unicode") == 0) return decode_pyunicode(value_addr, out);
    if (strcmp(tname, "PyColor") == 0) return describe_pycolor_json(value_addr, out);
    if (strcmp(tname, "Link") == 0) return describe_link_json(value_addr, out);
    // NoneType and anything else (nested instances/containers): omit.
    return false;
}

// ---------------------------------------------------------------------
// Children: obj.__dict__['children'] -> PyChildrenList ->
// its __dict__['_childrenObjects'] -> stock list -> ob_item array.
//
// Unwrapped repeatedly rather than bailing at the first non-list: a ButtonGroup
// nests one children-list wrapper inside another, and stopping early made the
// agent dialogue's buttons read as absent while plainly on screen.
// ---------------------------------------------------------------------
#define MAX_CHILDREN_UNWRAP 4

static bool find_children_objects(uint64_t wrapper, uint64_t *out_value) {
    uint64_t wrapper_dict;
    if (!get_dict(wrapper, &wrapper_dict)) return false;
    DictEntry entries[64];
    int n = walk_dict_raw(wrapper_dict, entries, 64);
    for (int i = 0; i < n; i++) {  // first occurrence wins
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
    uint64_t ob_size = 0, ob_item = 0;
    if (!read_u64(child_objs_list + OFF_OB_SIZE, &ob_size)) return 0;
    if (!read_u64(child_objs_list + OFF_LIST_ITEMS, &ob_item)) return 0;
    if (ob_size > (uint64_t)max_out) ob_size = max_out;
    if (ob_size == 0) return 0;
    if (!read_mem(ob_item, out, (size_t)ob_size * 8)) return 0;
    return (int)ob_size;
}

// ---------------------------------------------------------------------
// The walk
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

    uint64_t dict_addr = 0, children_wrapper = 0;
    bool first_attr = true;

    if (get_dict(obj_addr, &dict_addr)) {
        static DictEntry entries[MAX_DICT_ENTRIES];       // static: see macOS's
        static unsigned char keybuf[MAX_DICT_ENTRIES][64]; // note on stack depth
        static size_t keylen[MAX_DICT_ENTRIES];
        static bool key_ok[MAX_DICT_ENTRIES];
        static bool is_children_key[MAX_DICT_ENTRIES];
        static bool suppressed[MAX_DICT_ENTRIES];
        // These are static rather than local because the macOS file crashed at
        // depth ~20 with them on the stack (~396KB a frame). The walk is single
        // threaded and does not re-enter a node's own dict while emitting it, so
        // one set is enough -- but note the recursion below must not read them
        // after descending, and it does not.
        int n = walk_dict_raw(dict_addr, entries, MAX_DICT_ENTRIES);

        for (int i = 0; i < n; i++)
            key_ok[i] = decode_pystr(entries[i].key_addr, keybuf[i], sizeof(keybuf[i]), &keylen[i]);
        for (int i = 0; i < n; i++) {
            is_children_key[i] = key_ok[i] && keylen[i] == 8 && memcmp(keybuf[i], "children", 8) == 0;
            if (is_children_key[i] && !children_wrapper) children_wrapper = entries[i].value_addr;
        }
        memset(suppressed, 0, sizeof(bool) * (n > 0 ? n : 1));
        // last-wins for ordinary attributes, first-wins for 'children'
        for (int i = 0; i < n; i++) {
            if (!key_ok[i] || is_children_key[i] || suppressed[i] || !entries[i].value_addr) continue;
            for (int j = i + 1; j < n; j++) {
                if (key_ok[j] && !is_children_key[j] && keylen[j] == keylen[i] &&
                    memcmp(keybuf[j], keybuf[i], keylen[i]) == 0) { suppressed[i] = true; break; }
            }
            if (suppressed[i]) continue;
            size_t before = out->len;
            if (!first_attr) buf_str(out, ",");
            buf_json_escape(out, keybuf[i], keylen[i]);
            buf_str(out, ":");
            if (!describe_primitive_json(entries[i].value_addr, out)) {
                out->len = before;  // roll back the comma and key too
                continue;
            }
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
// Main: persistent process, one request per binary frame
// ---------------------------------------------------------------------
static int read_full(int fd, void *buf, size_t n) {
    size_t got = 0;
    while (got < n) {
        int r = _read(fd, (char *)buf + got, (unsigned)(n - got));
        if (r <= 0) return 0;
        got += r;
    }
    return 1;
}

static int write_full(int fd, const void *buf, size_t n) {
    size_t put = 0;
    while (put < n) {
        int r = _write(fd, (const char *)buf + put, (unsigned)(n - put));
        if (r <= 0) return 0;
        put += r;
    }
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: tree_walker <pid>\n"); return 2; }
    DWORD pid = (DWORD)strtoul(argv[1], NULL, 10);

    g_process = OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!g_process) {
        fprintf(stderr, "OpenProcess(%lu) failed: %lu\n", (unsigned long)pid, GetLastError());
        return 1;
    }
    g_pages = (PageSlot *)calloc(PAGE_CACHE_SLOTS, sizeof(PageSlot));
    if (!g_pages) { fprintf(stderr, "out of memory\n"); return 1; }

    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    fprintf(stderr, "ready\n");
    fflush(stderr);

    Buf out;
    buf_init(&out);

    for (;;) {
        unsigned char req[8 + 8 + 8 + 4 + 4];
        if (!read_full(_fileno(stdin), req, sizeof(req))) break;
        uint64_t root, metatype, str_type;
        uint32_t max_depth, max_nodes;
        memcpy(&root, req, 8);
        memcpy(&metatype, req + 8, 8);
        memcpy(&str_type, req + 16, 8);
        memcpy(&max_depth, req + 24, 4);
        memcpy(&max_nodes, req + 28, 4);

        g_metatype = metatype;
        g_str_type = str_type;
        g_node_budget = (int)max_nodes;
        g_page_epoch++;   // invalidate the page cache for this request
        g_reads = 0;

        out.len = 0;
        walk_node(root, 0, (int)max_depth, &out);

        uint64_t length = (uint64_t)out.len;
        if (!write_full(_fileno(stdout), &length, 8)) break;
        if (!write_full(_fileno(stdout), out.p, out.len)) break;
    }
    CloseHandle(g_process);
    return 0;
}
