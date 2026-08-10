"""Feasibility probe for the Windows host: is the client readable, and does the
macOS decoder's struct layout transfer to this binary?

Issue #176 lists four unverified things and says the first is serious: "There is
no Windows machine in this environment ... a Windows host would ship wholly
unexercised."  There is one now, with a live client, so this answers what can be
answered by reading and nothing else -- it opens the process read-only, sends no
input, and writes nothing to the client.

It answers, in order:

1. **Is ``ReadProcessMemory`` permitted** against the EVE client under current
   Windows protections and whatever anti-cheat it ships.
2. **Is this the same Python build** as the macOS client.
3. **Do the hardcoded offsets transfer**, which the issue calls "the whole
   question".  Each one is *measured* against objects whose correct decoding is
   checkable, not assumed and not taken from the 2019 C# reader -- which is
   32-bit throughout and therefore cannot answer it.
4. **Can the root be found**, which is where this port departs from macOS.

Every verdict is printed with the evidence that produced it, so a future build
that disagrees says so rather than being decoded wrongly in silence.

Usage::

    python probe.py                 # find the client, run every check
    python probe.py --pid 1234      # a specific process
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import time
from collections import Counter
from dataclasses import replace

from eve_mem import (
    AttachFailed,
    Layout,
    ProcessReader,
    PyReader,
    Types,
    find_client_pid,
    module_bases,
    module_exports,
)

# Objects are 8-byte aligned and ob_type sits at +8, so a pointer to a type found
# at address A is the ob_type field of a candidate object at A-8.
OB_TYPE_OFFSET = 8

# Enough samples to make a per-offset verdict a measurement rather than an
# anecdote, and few enough that the scan stops early on a busy client.
SAMPLE_TARGET = 4000


def ok(label: str, detail: str = "") -> None:
    print(f"  [ok]   {label}" + (f"  {detail}" if detail else ""))


def bad(label: str, detail: str = "") -> None:
    print(f"  [FAIL] {label}" + (f"  {detail}" if detail else ""))


def note(label: str, detail: str = "") -> None:
    print(f"  [--]   {label}" + (f"  {detail}" if detail else ""))


def section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def scan_for_pointer(reader: ProcessReader, value: int, limit: int) -> list[int]:
    """Addresses of 8-aligned words holding ``value``, up to ``limit`` of them."""
    needle = struct.pack("<Q", value)
    hits: list[int] = []
    for region in reader.regions():
        if region.size > (256 << 20):
            continue
        data = reader.try_read(region.base, region.size)
        if data is None:
            continue
        pos = 0
        while True:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            if pos % 8 == 0:
                hits.append(region.base + pos)
                if len(hits) >= limit:
                    return hits
            pos += 1
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=None)
    args = parser.parse_args()

    if struct.calcsize("P") != 8:
        print("this must run under 64-bit Python to read a 64-bit client")
        return 2

    failures = 0

    # ----------------------------------------------------------------- attach
    section("1. Attaching to the client")

    pid = args.pid or find_client_pid()
    if pid is None:
        bad("no EVE client found", "looked for bin64/exefile.exe")
        return 2
    note("client pid", str(pid))

    started = time.time()
    try:
        reader = ProcessReader(pid)
    except AttachFailed as exc:
        bad("OpenProcess refused", str(exc))
        print()
        print("  Issue #176's third unverified item answered NO: the client cannot")
        print("  be opened for reading, so no host of this design is possible")
        print("  without changing how it attaches.")
        return 1
    ok(
        "OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION)",
        f"{(time.time()-started)*1000:.1f}ms, no elevation, no debug privilege",
    )

    bases = module_bases(pid)
    main_base = bases.get("exefile.exe")
    if main_base is None:
        bad("exefile.exe not among the modules")
        return 2

    header = reader.try_read(main_base, 0x40)
    if header is None or header[:2] != b"MZ":
        bad("ReadProcessMemory returned nothing at the image base")
        failures += 1
    else:
        ok("ReadProcessMemory works", f"read the PE header at 0x{main_base:X}")

    regions = list(reader.regions())
    total = sum(r.size for r in regions)
    ok(
        "VirtualQueryEx enumerates the address space",
        f"{len(regions)} readable regions, {total/(1<<30):.2f} GiB",
    )

    # ------------------------------------------------------------ python27.dll
    section("2. Is this the same Python build as the macOS client?")

    py_base = bases.get("python27.dll")
    if py_base is None:
        bad("python27.dll is not loaded", "the decoder assumes CPython 2.7")
        return 1
    ok("python27.dll is loaded", f"base 0x{py_base:X}")
    blue = bases.get("blue.DLL") or bases.get("blue.dll")
    if blue:
        ok("blue.DLL is loaded", "the C-extension layer macOS names as the widget wrapper")
    else:
        note("blue.DLL is NOT loaded", "the custom-dict decoding below may not apply")

    exports = module_exports(reader, py_base)
    ok("export directory parsed", f"{len(exports)} named exports")

    types = Types.from_exports(exports)
    missing = [
        n
        for n in ("type", "str", "int", "long", "float", "unicode", "list", "dict")
        if n not in types.by_name
    ]
    if missing:
        bad("type objects missing from the exports", ", ".join(missing))
        return 1
    ok(
        "type objects resolved by name, not by heuristic",
        f"type=0x{types.by_name['type']:X}, str=0x{types.by_name['str']:X}",
    )
    note(
        "",
        "this is what removes macOS's metaclass bootstrap and its stale-seed trap",
    )

    # ------------------------------------------------------------- the header
    section("3. The PyObject header")

    L = Layout()
    py = PyReader(reader, L, types)

    metatype = types.by_name["type"]
    if py.type_of(metatype) == metatype:
        ok("type(type) is type", f"so ob_type is at +0x{L.ob_type:02X}, as on macOS")
    else:
        bad("type(type) is not type at +0x%02X" % L.ob_type)
        return 1

    named = {n: py.type_name_of_type(a) for n, a in types.by_name.items() if n != "NoneType"}
    disagree = {n: v for n, v in named.items() if v != n}
    if not disagree:
        ok(
            "every exported type object names itself through tp_name",
            f"tp_name at +0x{L.tp_name:02X}, {len(named)} of {len(named)}",
        )
    else:
        bad("tp_name disagrees", repr(disagree))
        failures += 1

    # -------------------------------------------------------------- str chars
    section("4. Where a str's characters start  (the LP64 / LLP64 question)")

    print("  PyStringObject is `PyObject_VAR_HEAD; long ob_shash; int ob_sstate;")
    print("  char ob_sval[1]`.  An 8-byte ob_shash puts the characters at +0x24,")
    print("  which is what macOS reads; a 4-byte one puts them at +0x20.  Decided")
    print("  by reading rather than by reasoning about the ABI:")
    print()

    started = time.time()
    hits = scan_for_pointer(reader, types.by_name["str"], SAMPLE_TARGET)
    candidates = [h - OB_TYPE_OFFSET for h in hits]
    note("str candidates", f"{len(candidates)} found in {time.time()-started:.1f}s")

    def score(offset: int):
        """Three independent tests per candidate at one candidate offset.

        The NUL count on its own is weak -- a short string finds a zero byte
        almost anywhere -- so it is reported but not decided on.  What decides is
        `printable`, and `states`, which reads the word the *other* layout would
        put the characters in: that is ob_sstate, which CPython only ever sets to
        0, 1 or 2.
        """
        terminated = printable = 0
        states: Counter = Counter()
        for address in candidates:
            size = reader.i64(address + L.ob_size)
            if size is None or not (0 <= size <= 4096):
                continue
            raw = reader.try_read(address + offset, size + 1)
            if raw is None or raw[size] != 0:
                continue
            terminated += 1
            if size and all(32 <= b < 127 for b in raw[:size]):
                printable += 1
            state = reader.u32(address + offset - 4)
            if state is not None:
                states[state] += 1
        return terminated, printable, states

    results = {offset: score(offset) for offset in (0x20, 0x24)}
    for offset, (terminated, printable, states) in results.items():
        sane = sum(v for k, v in states.items() if k in (0, 1, 2))
        note(
            f"characters at +0x{offset:02X}",
            f"{terminated} NUL-terminated, {printable} fully printable, "
            f"{sane}/{sum(states.values())} preceded by a legal ob_sstate",
        )

    def confidence(offset: int) -> int:
        terminated, printable, states = results[offset]
        legal = sum(v for k, v in states.items() if k in (0, 1, 2))
        return printable + legal

    winner = max(results, key=confidence)
    other = 0x20 if winner == 0x24 else 0x24
    if confidence(winner) > 4 * max(1, confidence(other)):
        ok(
            f"a str's characters start at +0x{winner:02X}",
            "same as macOS" if winner == 0x24 else "DIFFERENT from macOS's +0x24",
        )
        L = replace(L, str_chars=winner)
        py = PyReader(reader, L, types)
    else:
        bad(
            "the two candidate offsets are not separated by the evidence",
            "decide this by hand before trusting any tree",
        )
        return 1

    samples = []
    for address in candidates:
        value = py.read_str(address)
        if value and 6 <= len(value) <= 40 and all(32 <= b < 127 for b in value):
            samples.append(value.decode("ascii"))
        if len(samples) >= 6:
            break
    if samples:
        ok("strings decode", ", ".join(repr(s) for s in samples))
    else:
        bad("no sampled string decodes to readable text")
        failures += 1

    # ---------------------------------------------------------------- int size
    section("5. How wide a Python 2 int is")

    print("  PyIntObject.ob_ival is a bare `long`, so this is the same fact as")
    print("  section 4 rather than a second one: whichever answer ob_shash gave")
    print("  for sizeof(long) applies here too.  Corroborated rather than")
    print("  re-decided, because the candidates cannot be filtered as cleanly --")
    print("  a word pointing at PyInt_Type is often not an int object at all.")
    print()

    width = 8 if L.str_chars == 0x24 else 4
    L = replace(L, int_value_size=width)
    py = PyReader(reader, L, types)
    ok(
        f"ob_ival is {width} bytes",
        "LP64, as on macOS" if width == 8 else "LLP64 -- DIFFERENT from macOS",
    )

    int_hits = scan_for_pointer(reader, types.by_name["int"], SAMPLE_TARGET)
    values = []
    for hit in int_hits:
        address = hit - OB_TYPE_OFFSET
        refcount = reader.i64(address)
        if refcount is None or not (0 < refcount < 10_000_000):
            continue
        value = py.read_int(address)
        if value is not None:
            values.append(value)
    if values:
        small = sum(1 for v in values if -(1 << 31) < v < (1 << 31))
        note(
            "sampled ints",
            f"{len(values)} with a plausible refcount, "
            f"{small} inside 32 bits, range {min(values)}..{max(values)}",
        )

    # ------------------------------------------------------- unicode width
    section("5b. How wide a Python 2 unicode character is")

    print("  `Py_UNICODE` is `wchar_t`, so this is a *build option* rather than a")
    print("  platform constant: a CPython 2.7 configured --enable-unicode=ucs4")
    print("  stores 4 bytes per character and the stock Windows build stores 2.")
    print("  Reading it wrong drops every unicode value rather than garbling it,")
    print("  because UTF-16 bytes read as UTF-32 land on unassigned planes and")
    print("  raise -- which is why this hid for a while: `str` decoded fine and")
    print("  only the values EVE stores as `unicode` went missing, among them")
    print("  every context-menu entry's text.")
    print()

    uni_hits = scan_for_pointer(reader, types.by_name["unicode"], SAMPLE_TARGET)
    uni_candidates = [h - OB_TYPE_OFFSET for h in uni_hits]
    note("unicode candidates", str(len(uni_candidates)))

    def score_width(width: int) -> tuple[int, list[str]]:
        good, samples = 0, []
        probe_layout = replace(L, unicode_char_size=width)
        probe_py = PyReader(reader, probe_layout, types)
        for address in uni_candidates:
            refcount = reader.i64(address)
            if refcount is None or not (0 < refcount < 10_000_000):
                continue
            value = probe_py.read_unicode(address)
            if not value:
                continue
            if all(32 <= ord(c) < 127 or c in "\t\n" for c in value):
                good += 1
                if 4 <= len(value) <= 40 and len(samples) < 5:
                    samples.append(value)
        return good, samples

    widths = {w: score_width(w) for w in (2, 4)}
    for width, (good, _) in widths.items():
        note(f"{width} bytes per character", f"{good} decode to readable text")
    best = max(widths, key=lambda w: widths[w][0])
    worst = 2 if best == 4 else 4
    if widths[best][0] > 4 * max(1, widths[worst][0]):
        ok(
            f"unicode is UCS-{best} ({best} bytes per character)",
            "same as macOS" if best == 4 else "DIFFERENT from macOS's UCS-4",
        )
        L = replace(L, unicode_char_size=best)
        py = PyReader(reader, L, types)
        if widths[best][1]:
            ok("unicode values decode", ", ".join(repr(s) for s in widths[best][1]))
    else:
        bad("the two character widths are not separated by the evidence")
        failures += 1

    # ------------------------------------------------------------- Blue's dict
    section("6. Blue's custom dict")

    print("  The part issue #176 calls 'precisely the part tree_walker does")
    print("  natively', and the part the 2019 C# reader cannot corroborate --")
    print("  PyDict.cs decodes a stock PyDictObject, which this is not.")
    print()

    from tree_walker import TP_DICTOFFSET, Walker, find_ui_root  # noqa: E402

    walker = Walker(reader, py)
    started = time.time()
    root = find_ui_root(reader, py)
    root_seconds = time.time() - started
    if root is None:
        bad("no UIRoot found", "see section 7")
        return 1

    dict_address = walker.get_dict(root)
    if dict_address is None:
        bad("the UI root has no dict at the offset its type states")
        return 1
    root_type = reader.u64(root + L.ob_type)
    stated = reader.i64(root_type + TP_DICTOFFSET) if root_type else None
    if stated == L.widget_dict:
        ok(
            "the widget's dict is where its own type object says it is",
            f"tp_dictoffset={stated}, which is what the decoder uses",
        )
    else:
        note(
            "the type object states a different dict offset",
            f"tp_dictoffset={stated}, decoder uses +0x{L.widget_dict:02X}",
        )

    entries = walker.dict_items(dict_address)
    keys = [k.decode("latin-1") for k, _ in entries]
    ok(
        f"the root's dict decodes at header 0x{L.dict_header:X}, entries {L.dict_entry_size}",
        f"{len(entries)} keys",
    )
    note("", ", ".join(repr(k) for k in keys[:8]))
    if "children" in keys:
        ok("'children' is present", "the walk the 2019 reader describes is intact")
    else:
        bad("'children' is not among the root's keys")
        failures += 1

    # ------------------------------------------------------------------- root
    section("7. Finding the root")

    repr_re = re.compile(rb"<([A-Za-z_][A-Za-z0-9_]{2,40}) object at 0[Xx]([0-9A-Fa-f]{6,16})>")
    seeds = 0
    started = time.time()
    for region in reader.regions():
        if region.size > (256 << 20):
            continue
        data = reader.try_read(region.base, region.size)
        if data is None:
            continue
        seeds += sum(1 for _ in repr_re.finditer(data))
        if seeds > 100:
            break
    note(
        "macOS's repr-text seeds",
        f"{seeds} found in {time.time()-started:.1f}s",
    )
    if seeds == 0:
        ok(
            "the macOS root-discovery route does not exist on this client",
            "a finding, not a failure -- see the type-object route below",
        )
    else:
        note("", "the repr route may be usable here as well; macOS's is cheaper")

    ok("UIRoot found by the type-object route", f"0x{root:X} in {root_seconds:.0f}s")
    name = None
    for key, value in entries:
        if key == b"_name":
            name = walker.primitive(value)
    note("", f"_name={name!r}; cache this for the session, as the macOS host does")

    # ------------------------------------------------------------------- tree
    section("8. One whole tree")

    reader.reads = 0  # the scans above are not part of what a reading costs
    started = time.time()
    tree = walker.read_tree(root)
    elapsed = time.time() - started

    def count(node):
        return 1 + sum(count(c) for c in node["children"])

    total_nodes = count(tree)
    with_region = _count_with_region(tree)
    ok(
        "the tree reads",
        f"{total_nodes} nodes in {elapsed:.1f}s ({reader.reads} ReadProcessMemory calls)",
    )
    ok(
        "nodes carry a display region",
        f"{with_region} of {total_nodes} -- the four keys ParseUserInterface navigates by",
    )
    types_seen = Counter(n["pythonObjectTypeName"] for n in _walk(tree))
    unnamed = types_seen.get(None, 0)
    if unnamed:
        note("nodes with no type name", str(unnamed))
    ok("most common classes", ", ".join(f"{t}({c})" for t, c in types_seen.most_common(5)))

    # ------------------------------------------------------------------- done
    section("Verdict")
    print(f"  layout for this build:")
    print(f"    ob_type          +0x{L.ob_type:02X}")
    print(f"    tp_name          +0x{L.tp_name:02X}")
    print(f"    str characters   +0x{L.str_chars:02X}"
          f"{'   <- differs from macOS (+0x24)' if L.str_chars != 0x24 else ''}")
    print(f"    int value width  {L.int_value_size}"
          f"{'          <- differs from macOS (8)' if L.int_value_size != 8 else ''}")
    print(f"    widget dict      +0x{L.widget_dict:02X}")
    print(f"    dict header      0x{L.dict_header:02X}, "
          f"{L.dict_inline_entries} inline entries of {L.dict_entry_size} bytes")
    reader.close()
    if failures:
        print(f"\n  {failures} check(s) failed.")
        return 1
    print("\n  Every check passed.  See FINDINGS.md for what it means.")
    return 0


def _walk(node):
    yield node
    for child in node["children"]:
        yield from _walk(child)


def _count_with_region(tree) -> int:
    keys = ("_displayX", "_displayY", "_displayWidth", "_displayHeight")
    return sum(
        1 for n in _walk(tree) if all(k in n["dictEntriesOfInterest"] for k in keys)
    )


if __name__ == "__main__":
    sys.exit(main())
