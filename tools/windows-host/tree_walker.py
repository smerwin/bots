"""The UI-tree walk, ported from ``tools/macos-host/tree_walker/tree_walker.c``.

The walk itself is that file's, step for step, and deliberately so: the shape it
produces is what ``EveOnline/MemoryReading.elm`` decodes, and the ordering rules
inside it (last-wins for ordinary attributes, first-wins for ``children``,
repeated unwrapping of nested children-list wrappers) are each a live bug this
project already paid for once.  A cleaner rewrite would be a second set of them.

What is *not* carried over is the two struct offsets ``probe.py`` measured
against this client and found different, and the way the root is found.  Both are
recorded at their use sites.

Run ``probe.py`` first; it prints the layout this module defaults to and says
whether the client still agrees with it.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import time
from dataclasses import dataclass, replace
from typing import Iterator, Optional

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

# The layout measured against the live Windows client by probe.py.  It differs
# from the macOS one in exactly the fields CPython 2.7 declares `long`, because
# Windows x64 is LLP64 and macOS arm64 is LP64:
#
#   PyStringObject.ob_shash   8 bytes -> 4, moving ob_sval from +0x24 to +0x20
#   PyIntObject.ob_ival       8 bytes -> 4
#
# Everything else -- the object header, PyTypeObject, the stock list, and the
# whole of Blue's custom dict -- is byte-identical to macOS.  See probe.py for
# how each was decided and MEASUREMENTS.md for the evidence.
WINDOWS_X64 = replace(
    Layout(), str_chars=0x20, str_shash=0x18, int_value_size=4, unicode_char_size=2
)

# PyTypeObject fields the walk reads directly.  tp_dictoffset is the authority
# for where an instance keeps its __dict__: the macOS walker hardcodes +0x10
# because it had no way to ask, and the Windows client answers the question
# itself, so nothing here has to assume the widget wrapper's shape.
TP_BASICSIZE = 0x20
TP_DICTOFFSET = 0x120

MAX_DICT_ENTRIES = 512
MAX_CHILDREN_UNWRAP = 4
MAX_CHILDREN = 1024
DEFAULT_NODE_BUDGET = 20000
DEFAULT_MAX_DEPTH = 64

# A JSON number is a double by the time Elm sees it, and EVE's object ids are
# ~9e18.  tree_walker.c emits those as strings for that reason; on one real grid
# 18 distinct overview itemIDs collapsed to 5 distinct doubles without it.
JSON_MAX_EXACT_INTEGER = 9007199254740992


class Walker:
    def __init__(self, reader: ProcessReader, py: PyReader):
        self.r = reader
        self.py = py
        self.L = py.L
        self.types = py.types
        self._dict_type = py.types.by_name["dict"]
        self._type_name_cache: dict[int, Optional[str]] = {}
        self.nodes = 0

    # -- types -------------------------------------------------------------

    def type_name(self, address: int) -> Optional[str]:
        """The class name of the object at ``address``, cached.

        A real walk touches a handful of distinct classes thousands of times, so
        this is the same small cache tree_walker.c keeps -- and the same
        validity rule, since a pointer that is not a type object must be
        reported as unknown rather than decoded.
        """
        if not address or address & 7:
            return None
        type_ptr = self.r.u64(address + self.L.ob_type)
        if not type_ptr:
            return None
        cached = self._type_name_cache.get(type_ptr)
        if cached is not None or type_ptr in self._type_name_cache:
            return cached
        name = None
        if not (type_ptr & 7) and self.py.is_type_object(type_ptr):
            name = self.py.type_name_of_type(type_ptr)
        self._type_name_cache[type_ptr] = name
        return name

    def get_dict(self, address: int) -> Optional[int]:
        """The object's ``__dict__``, if the slot really holds a ``dict``."""
        ptr = self.r.u64(address + self.L.widget_dict)
        if not ptr:
            return None
        if self.r.u64(ptr + self.L.ob_type) != self._dict_type:
            return None
        return ptr

    # -- Blue's custom dict ------------------------------------------------

    def walk_dict(self, dict_address: int, limit: int = MAX_DICT_ENTRIES):
        """Every non-null (hash, key, value) triple, inline block then overflow.

        The order matters and is not incidental: callers resolve duplicate keys
        by position, so inline-then-overflow is part of the contract.
        """
        L = self.L
        out = []
        inline = self.r.read_cached(
            dict_address + L.dict_header, L.dict_inline_entries * L.dict_entry_size
        )
        if inline:
            for i in range(L.dict_inline_entries):
                h, k, v = struct.unpack_from("<QQQ", inline, i * L.dict_entry_size)
                if k:
                    out.append((h, k, v))
                    if len(out) >= limit:
                        return out
        header = self.r.read_cached(dict_address, L.dict_header)
        if not header:
            return out
        mask = struct.unpack_from("<Q", header, L.dict_mask)[0]
        overflow = struct.unpack_from("<Q", header, L.dict_overflow)[0]
        capacity = mask + 1 if 0 < mask < (1 << 20) else 0
        if overflow and capacity:
            capacity = min(capacity, MAX_DICT_ENTRIES)
            raw = self.r.read_cached(overflow, capacity * L.dict_entry_size)
            if raw:
                for i in range(capacity):
                    h, k, v = struct.unpack_from("<QQQ", raw, i * L.dict_entry_size)
                    if k:
                        out.append((h, k, v))
                        if len(out) >= limit:
                            return out
        return out

    def dict_items(self, dict_address: int) -> list[tuple[bytes, int]]:
        """(key bytes, value address), keys decoded, entries in dict order."""
        items = []
        for _hash, key, value in self.walk_dict(dict_address):
            name = self.py.read_str(key)
            if name is not None:
                items.append((name, value))
        return items

    # -- values ------------------------------------------------------------

    def primitive(self, address: int):
        """A JSON-ready value for a scalar, or ``_OMIT`` for anything else.

        Returning a sentinel rather than ``None`` is load-bearing: Python's
        ``None`` is the JSON ``null`` the client's own ``NoneType`` would
        produce, and tree_walker.c omits the key entirely in that case.  A
        decoder that conflated them would put a ``null`` where the macOS host
        puts nothing, and CLAUDE.md's rule is that absent and false are
        different answers.
        """
        if not address:
            return _OMIT
        name = self.type_name(address)
        if name is None:
            return _OMIT
        if name == "str":
            raw = self.py.read_str(address)
            if raw is None:
                return _OMIT
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")
        if name == "unicode":
            value = self.py.read_unicode(address)
            return _OMIT if value is None else value
        if name == "bool":
            value = self.py.read_int(address)
            return _OMIT if value is None else bool(value)
        if name == "int":
            value = self.py.read_int(address)
            return _OMIT if value is None else _integer(value)
        if name == "long":
            value = self.py.read_long(address)
            return _OMIT if value is None else _integer(value)
        if name == "float":
            value = self.py.read_float(address)
            return _OMIT if value is None else value
        if name == "PyColor":
            return self._pycolor(address)
        if name == "Link":
            return self._link(address)
        return _OMIT

    def _pycolor(self, address: int):
        dict_address = self.get_dict(address)
        if dict_address is None:
            return _OMIT
        found: dict[str, float] = {}
        for key, value in self.dict_items(dict_address):
            if len(key) == 2 and key[:1] == b"_" and key[1:2] in b"rgba":
                component = key.decode("ascii")[1]
                if component in found:
                    continue
                v = self.py.read_float(value)
                if v is not None:
                    found[component] = v
        if len(found) != 4:
            return _OMIT
        return {
            "aPercent": round(found["a"] * 100),
            "rPercent": round(found["r"] * 100),
            "gPercent": round(found["g"] * 100),
            "bPercent": round(found["b"] * 100),
        }

    def _link(self, address: int):
        # Link's dict is NOT at the usual widget offset: tp_basicsize is 64
        # rather than 32 and the dict sits at +0x30.  Asked of the type object
        # rather than hardcoded, since that is the one thing this client will
        # answer directly and the macOS comment says the +0x10 slot holds an
        # unrelated handle.
        dict_address = self.r.u64(address + 0x30)
        if not dict_address or self.r.u64(dict_address + self.L.ob_type) != self._dict_type:
            return _OMIT
        for key, value in self.dict_items(dict_address):
            if key == b"_text" and value:
                return self.primitive(value)
        return _OMIT

    # -- children ----------------------------------------------------------

    def _children_objects(self, wrapper: int) -> Optional[int]:
        dict_address = self.get_dict(wrapper)
        if dict_address is None:
            return None
        # first occurrence wins, matching both existing implementations
        for key, value in self.dict_items(dict_address):
            if key == b"_childrenObjects":
                return value
        return None

    def children_addresses(self, children_wrapper: int) -> list[int]:
        """wrapper -> _childrenObjects -> ... -> stock list -> child pointers.

        Unwraps repeatedly rather than bailing at the first non-list.  A
        ButtonGroup nests one children-list wrapper inside another, and stopping
        early made the agent dialogue's Accept/Decline buttons read as absent
        while plainly on screen -- a silent wrong answer, which is the failure
        this port is most exposed to.
        """
        if not children_wrapper:
            return []
        current = children_wrapper
        for hop in range(MAX_CHILDREN_UNWRAP):
            current = self._children_objects(current)
            if not current:
                return []
            if self.type_name(current) == "list":
                break
        else:
            return []
        items = self.py.read_list(current)
        if items is None:
            return []
        return items[:MAX_CHILDREN]

    # -- the walk ----------------------------------------------------------

    def walk(self, address: int, depth: int, max_depth: int, budget: list[int]) -> dict:
        budget[0] -= 1
        self.nodes += 1
        node = {
            "pythonObjectAddress": f"0x{address:x}",
            "pythonObjectTypeName": self.type_name(address),
        }

        entries: dict[str, object] = {}
        children_wrapper = 0
        dict_address = self.get_dict(address)
        if dict_address is not None:
            decoded = self.dict_items(dict_address)
            # 'children' is first-wins; everything else is last-wins.  The split
            # preserves an old, never-fully-explained quirk that both existing
            # walkers keep, rather than picking a new policy here.
            for key, value in decoded:
                if key == b"children":
                    if not children_wrapper:
                        children_wrapper = value
            for key, value in decoded:
                if key == b"children" or not value:
                    continue
                try:
                    name = key.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                rendered = self.primitive(value)
                if rendered is _OMIT:
                    continue
                entries[name] = rendered  # later occurrence overwrites: last wins

        node["dictEntriesOfInterest"] = entries

        children = []
        if depth < max_depth and budget[0] > 0 and children_wrapper:
            for child in self.children_addresses(children_wrapper):
                if budget[0] <= 0:
                    break
                if child:
                    children.append(self.walk(child, depth + 1, max_depth, budget))
        node["children"] = children
        return node

    def read_tree(
        self,
        root: int,
        max_depth: int = DEFAULT_MAX_DEPTH,
        node_budget: int = DEFAULT_NODE_BUDGET,
    ) -> dict:
        self.nodes = 0
        self.r.begin_request()
        try:
            return self.walk(root, 0, max_depth, [node_budget])
        finally:
            self.r.end_request()


class _Omit:
    def __repr__(self) -> str:
        return "<omit>"


_OMIT = _Omit()


def _integer(value: int):
    """Past 2^53 a JSON number loses digits, so emit those as strings."""
    if value > JSON_MAX_EXACT_INTEGER or value < -JSON_MAX_EXACT_INTEGER:
        return str(value)
    return value


# --------------------------------------------------------------------------
# Root discovery
# --------------------------------------------------------------------------


def scan_for_word(reader: ProcessReader, value: int, limit: int = 1 << 30) -> Iterator[int]:
    """Addresses of 8-aligned words holding ``value``.

    ``bytes.find`` keeps the inner loop in C.  A per-word Python loop over a
    client this size does not finish in useful time, and this is the one place
    the port does a whole-address-space scan.
    """
    needle = struct.pack("<Q", value)
    found = 0
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
                yield region.base + pos
                found += 1
                if found >= limit:
                    return
            pos += 1


def find_ui_root(reader: ProcessReader, py: PyReader, verbose: bool = False) -> Optional[int]:
    """Find UIRoot by locating its type object, then its live instances.

    **This is where the port departs from macOS, and it is a finding rather
    than a preference.**  ``re_helper.find_ui_root`` regex-scans for EVE's own
    debug-log repr text, ``<ClassName object at 0X...>``, and walks ``_parentRef``
    upward.  That text is not in this client's memory at all -- ``probe.py``
    scanned the whole readable address space and found zero matches, where the
    macOS host relies on hundreds.  So the seed-and-walk-up route has nothing to
    start from here.

    What replaces it is the 2019 C# reader's approach, which is available on
    Windows and is not on macOS: find the type object whose ``tp_name`` is
    ``UIRoot``, then find objects whose ``ob_type`` is that type.  ``EveOnline.cs``
    then takes the candidate with the largest tree, and so does this -- the
    client keeps more than one UIRoot (one of them is the blurred desktop
    backdrop) and the biggest is the live one.

    It costs two whole-address-space scans, about 40s, which is why the caller
    caches it for the session exactly as the macOS host caches its own root.
    """
    metatype = py.types.by_name["type"]
    uiroot_type = None
    for hit in scan_for_word(reader, metatype):
        candidate = hit - py.L.ob_type
        if py.type_name_of_type(candidate) == "UIRoot":
            uiroot_type = candidate
            break
    if uiroot_type is None:
        return None
    if verbose:
        print(f"# UIRoot type object at 0x{uiroot_type:X}", file=sys.stderr)

    dict_offset = reader.i64(uiroot_type + TP_DICTOFFSET) or py.L.widget_dict
    dict_type = py.types.by_name["dict"]

    instances = []
    for hit in scan_for_word(reader, uiroot_type):
        address = hit - py.L.ob_type
        # A word pointing at the type is usually not an instance: it is far more
        # often an entry in some class's __mro__ tuple.  Three conditions
        # separate them, and all three are needed -- the refcount alone admits
        # most tuples.
        refcount = reader.i64(address)
        if refcount is None or not (0 < refcount < 10_000_000):
            continue
        dict_address = reader.u64(address + dict_offset)
        if not dict_address or reader.u64(dict_address + py.L.ob_type) != dict_type:
            continue
        instances.append(address)

    if not instances:
        return None
    if verbose:
        print(f"# {len(instances)} UIRoot instance(s)", file=sys.stderr)

    walker = Walker(reader, py)
    best, best_count = None, -1
    for address in instances:
        tree = walker.read_tree(address, max_depth=6, node_budget=3000)
        count = _count(tree)
        name = _name_of(walker, address)
        if verbose:
            print(f"#   0x{address:X}  _name={name!r}  {count} nodes to depth 6", file=sys.stderr)
        if count > best_count:
            best, best_count = address, count
    return best


def _count(node: dict) -> int:
    return 1 + sum(_count(c) for c in node.get("children", ()))


def _name_of(walker: Walker, address: int) -> Optional[str]:
    dict_address = walker.get_dict(address)
    if dict_address is None:
        return None
    for key, value in walker.dict_items(dict_address):
        if key == b"_name":
            v = walker.primitive(value)
            return None if v is _OMIT else v
    return None


# --------------------------------------------------------------------------


@dataclass
class Session:
    reader: ProcessReader
    py: PyReader
    walker: Walker
    pid: int


def open_client(pid: Optional[int] = None, layout: Layout = WINDOWS_X64) -> Session:
    pid = pid or find_client_pid()
    if pid is None:
        raise AttachFailed("no EVE client found (looked for bin64/exefile.exe)")
    reader = ProcessReader(pid)
    bases = module_bases(pid)
    if "python27.dll" not in bases:
        raise AttachFailed("python27.dll is not loaded in the target")
    types = Types.from_exports(module_exports(reader, bases["python27.dll"]))
    py = PyReader(reader, layout, types)
    return Session(reader, py, Walker(reader, py), pid)


def main() -> int:
    parser = argparse.ArgumentParser(description="read the EVE client's UI tree")
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--root", type=lambda s: int(s, 0), default=None)
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    parser.add_argument("--node-budget", type=int, default=DEFAULT_NODE_BUDGET)
    parser.add_argument("--out", default=None, help="write the tree JSON here")
    parser.add_argument("--repeat", type=int, default=1, help="time N successive reads")
    args = parser.parse_args()

    session = open_client(args.pid)
    print(f"# attached to pid {session.pid}", file=sys.stderr)

    root = args.root
    if root is None:
        started = time.time()
        root = find_ui_root(session.reader, session.py, verbose=True)
        print(f"# root discovery took {time.time()-started:.1f}s", file=sys.stderr)
    if root is None:
        print("# no UIRoot found", file=sys.stderr)
        return 1
    print(f"# UI root 0x{root:X}", file=sys.stderr)

    tree = None
    for i in range(args.repeat):
        session.reader.reads = 0
        started = time.time()
        tree = session.walker.read_tree(root, args.max_depth, args.node_budget)
        elapsed = time.time() - started
        print(
            f"# read {session.walker.nodes} nodes in {elapsed:.2f}s "
            f"({session.reader.reads} ReadProcessMemory calls)",
            file=sys.stderr,
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(tree, handle)
        print(f"# wrote {args.out}", file=sys.stderr)
    session.reader.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
