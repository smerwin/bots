#!/usr/bin/env python3
"""Reverse-engineering helper for macos-host memory samples (see CLAUDE.md).

Loads regions.tsv, converts between dump-file offsets and target-process
virtual addresses in both directions, and can:
  - search memory.bin for a byte string and dump surrounding context
  - classify an arbitrary 8-byte value as a likely PyObject pointer by
    checking the CPython invariant that every valid PyTypeObject's own
    ob_type points to the 'type' metaclass (found empirically once per
    process and passed in via --metatype, or auto-detected)
  - dump an object's header and try to label each field
"""
import argparse
import bisect
import mmap
import os
import re
import struct
import subprocess
import sys
import threading


_UNSET = object()


def parse_pystr_chunk(chunk):
    """Parse a chunk read from addr+0x10 (the same window read_pystr and
    the batched paths below all use) into decoded string bytes, or None
    if the chunk didn't fully cover the string (caller should fall back
    to a direct, precisely-sized read at addr+0x24 in that case)."""
    if chunk is None or len(chunk) < 8:
        return None
    length = struct.unpack_from("<Q", chunk, 0)[0]
    if length > 1 << 20:
        return None
    char_off = 0x14  # 0x24 - 0x10, relative to this chunk's start
    if char_off + length <= len(chunk):
        return chunk[char_off:char_off + length]
    return None


class MemoryReaderBase:
    """Shared decode logic (read_cstr, read_pystr) for any backend that
    implements read_bytes(addr, n) -> bytes|None and read_u64(addr) ->
    int|None. Subclasses provide the actual byte source (a dump file's
    mmap, or a live process via a persistent helper process)."""

    def read_bytes_batch(self, requests):
        """requests: [(addr, n), ...] -> [bytes|None, ...], same order.
        Default sequential fallback (fine for the mmap-backed Sample,
        where there's no per-call round trip to save); LiveSample
        overrides this to actually pipeline the requests."""
        return [self.read_bytes(a, n) for a, n in requests]

    def read_cstr(self, addr, maxlen=64):
        b = self.read_bytes(addr, maxlen)
        if b is None:
            return None
        nul = b.find(b"\x00")
        return b if nul == -1 else b[:nul]

    # Covers header (0x24 bytes) + string data in one read for the common
    # case; only a real string longer than this falls back to a second,
    # precisely-sized read. Sized from real observed data (this session's
    # attribute names/labels top out around 40-45 chars, e.g. texture
    # paths like "res:/ui/Texture/WindowIcons/overview.png") rather than
    # a round number -- on a live UI tree with thousands of these reads
    # per cycle, the gap between 256 and what's actually needed is a
    # measurable chunk of total data volume (measured: ~58MB per full
    # tree read at 256; over-fetching on typically-short strings is a
    # real, not hypothetical, cost at this scale).
    _PYSTR_OPTIMISTIC_CHUNK = 96

    def read_pystr(self, addr):
        """Decode a compact-ASCII PyUnicode object: refcnt(8) type(8)
        length(8) hash(8) state(4)+pad(4), then `length` bytes of ASCII.

        Optimistically reads header+chars together in one call sized for
        the common case (short strings); only issues a second read for
        the rare longer string. Matters most for the live backend, where
        each read is a real round trip, not an mmap slice."""
        chunk = self.read_bytes(addr + 0x10, self._PYSTR_OPTIMISTIC_CHUNK)
        s = parse_pystr_chunk(chunk)
        if s is not None:
            return s
        if chunk is None or len(chunk) < 8:
            return None
        length = struct.unpack_from("<Q", chunk, 0)[0]
        if length > 1 << 20:
            return None
        data = self.read_bytes(addr + 0x24, length)
        if data is None or len(data) < length:
            return None
        return data


class Sample(MemoryReaderBase):
    """Backed by a memory_sample dump (regions.tsv + memory.bin) on disk.
    Good for offline RE / exploratory searches (find_all), but requires a
    multi-GB, multi-second full dump per snapshot -- see LiveSample for
    the fast path when only a handful of live values are needed."""

    def __init__(self, sample_dir):
        self.regions = []  # (addr, bytes_written, offset_in_dump)
        with open(f"{sample_dir}/regions.tsv") as f:
            next(f)
            for line in f:
                addr_hex, size_hex, prot, shared, status, offset_s, bytes_s = line.rstrip("\n").split("\t")
                bw = int(bytes_s)
                if bw == 0:
                    continue
                self.regions.append((int(addr_hex, 16), bw, int(offset_s)))
        self.regions.sort()
        self.addrs = [r[0] for r in self.regions]
        self.f = open(f"{sample_dir}/memory.bin", "rb")
        self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)

    def addr_to_offset(self, addr):
        i = bisect.bisect_right(self.addrs, addr) - 1
        if i < 0:
            return None
        start, bw, off = self.regions[i]
        if addr < start + bw:
            return off + (addr - start)
        return None

    def read_bytes(self, addr, n):
        off = self.addr_to_offset(addr)
        if off is None:
            return None
        return self.mm[off:off + n]

    def read_u64(self, addr):
        b = self.read_bytes(addr, 8)
        if b is None or len(b) < 8:
            return None
        return struct.unpack("<Q", b)[0]

    def find_all(self, needle: bytes, limit=None):
        results = []
        start = 0
        while limit is None or len(results) < limit:
            idx = self.mm.find(needle, start)
            if idx == -1:
                break
            results.append(idx)
            start = idx + 1
        return results


_LIVE_READER_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "live_reader", "live_reader")


class LiveSample(MemoryReaderBase):
    """Backed by a persistent, entitled helper process (live_reader) that
    reads the target process's memory directly via task_for_pid + repeated
    mach_vm_read_overwrite calls -- no dump file, no multi-GB write. This
    is the fast path: each read is one small round trip to an
    already-attached process instead of re-dumping gigabytes to re-read a
    handful of bytes.
    No find_all() / addr_to_offset(): those need a full dump to search
    over; use Sample for exploratory RE, LiveSample for repeated reads of
    already-known structures/addresses."""

    def __init__(self, pid, binary=_LIVE_READER_BIN):
        self.proc = subprocess.Popen(
            [binary, str(pid)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ready = self.proc.stderr.readline()
        if b"ready" not in ready:
            err = ready + self.proc.stderr.read()
            raise RuntimeError(f"live_reader failed to start: {err!r}")
        self.reads = 0        # logical reads (matches Sample's granularity)
        self.round_trips = 0  # actual pipe round trips -- what batching reduces
        self.bytes_read = 0
        self._buf = b""       # self-managed read-ahead buffer, see _read_exact
        self._buf_pos = 0

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=2)

    _FILL_SIZE = 1 << 20  # 1MB: how much to pull from the OS pipe per underlying read() call

    def _read_exact(self, n):
        """Like stdout.read(n) but backed by a large internal buffer, so
        many small protocol-level reads (an 8-byte length header, then a
        short payload, repeated per response in a batch) cost one Python
        function call against already-buffered memory instead of a
        syscall-backed .read() every time. Found necessary by profiling:
        813,809 individual BufferedReader.read() calls -- two per
        response (header + payload) across ~407,000 responses -- were
        the single largest cost in a real tree walk (0.792s of 2.794s
        total), bigger than build_tree's own Python-level overhead.
        io.BufferedReader already reduces *OS* syscalls via its own
        default buffer, but each .read() call still pays real
        Python/C-boundary-crossing overhead every time it's invoked --
        this collapses that call count by pulling much larger chunks
        (1MB) per underlying read instead of relying on BufferedReader's
        smaller default buffer size to happen to cover many small
        protocol reads without new fills."""
        while len(self._buf) - self._buf_pos < n:
            # read1(), not read(): read() blocks until it gets exactly
            # the requested size (or EOF), which would hang here if a
            # batch's total remaining response is smaller than
            # _FILL_SIZE -- live_reader has nothing more to send until
            # the *next* batch, so asking for more than that would block
            # forever waiting for data that isn't coming. read1() does
            # at most one underlying read and returns whatever's
            # immediately available (still blocks if truly nothing is
            # ready yet, which is correct -- we want to wait for *some*
            # data, just not demand a fixed large amount).
            chunk = self.proc.stdout.read1(self._FILL_SIZE)
            if not chunk:
                remaining = self._buf[self._buf_pos:]
                self._buf, self._buf_pos = b"", 0
                return remaining if remaining else None
            if self._buf_pos:
                self._buf = self._buf[self._buf_pos:]
                self._buf_pos = 0
            self._buf += chunk
        result = self._buf[self._buf_pos:self._buf_pos + n]
        self._buf_pos += n
        return result

    def read_bytes(self, addr, n):
        if not addr:
            return None
        self.reads += 1
        self.round_trips += 1
        try:
            self.proc.stdin.write(struct.pack("<QQ", addr, n))
            self.proc.stdin.flush()
            got_b = self._read_exact(8)
            if not got_b or len(got_b) < 8:
                return None
            got = struct.unpack("<Q", got_b)[0]
            if got == 0:
                return None
            data = self._read_exact(got)
            if not data or len(data) != got:
                return None
            self.bytes_read += got
            return data
        except (BrokenPipeError, OSError):
            return None

    def read_u64(self, addr):
        b = self.read_bytes(addr, 8)
        return struct.unpack("<Q", b)[0] if b and len(b) == 8 else None

    def read_bytes_batch(self, requests):
        """Pipeline: write every request while concurrently reading
        responses, instead of one blocking round trip per request. The
        actual mach_vm_read work is fast; what dominates is round-trip
        latency, so collapsing N round trips into 1 is the single biggest
        lever for this backend.

        The write and the read happen on separate threads, not
        sequentially (write-everything-then-read-everything). Found
        necessary the hard way: once the whole level of a breadth-first
        tree walk needed a single batch of ~6500 key-decode requests, the
        request payload alone (16 bytes/request) exceeded the OS pipe
        buffer (~64KB on macOS). A single `stdin.write()` call for that
        much data blocks once the pipe fills; live_reader.c's own reply
        write then blocks too once *its* output pipe fills, since nothing
        is draining it yet (we're still stuck inside the initial write);
        with both sides blocked on a full pipe waiting for the other to
        drain it, `read_bytes_batch` hung forever on any large enough
        batch. A background thread writing the request while the main
        thread concurrently reads responses removes the deadlock
        regardless of batch size, the standard fix for this exact
        bidirectional-pipe problem (the same reason
        `subprocess.communicate()` uses threads/select internally)."""
        if not requests:
            return []
        self.reads += len(requests)
        self.round_trips += 1
        try:
            payload = b"".join(struct.pack("<QQ", a or 0, n) for a, n in requests)

            write_error = []

            def writer():
                try:
                    self.proc.stdin.write(payload)
                    self.proc.stdin.flush()
                except (BrokenPipeError, OSError) as exc:
                    write_error.append(exc)

            t = threading.Thread(target=writer, daemon=True)
            t.start()

            results = []
            for a, n in requests:
                if not a:
                    # still consume the response live_reader will send for
                    # this slot (addr 0 -> mach_vm_read_overwrite fails ->
                    # got=0), keeps the request/response streams in lockstep
                    got_b = self._read_exact(8)
                    results.append(None)
                    continue
                got_b = self._read_exact(8)
                if not got_b or len(got_b) < 8:
                    results.append(None)
                    continue
                got = struct.unpack("<Q", got_b)[0]
                if got == 0:
                    results.append(None)
                    continue
                data = self._read_exact(got)
                if not data or len(data) != got:
                    results.append(None)
                    continue
                self.bytes_read += got
                results.append(data)
            t.join()
            if write_error:
                raise write_error[0]
            return results
        except (BrokenPipeError, OSError):
            return [None] * len(requests)


def type_name_if_valid_type(sample: Sample, type_ptr, metatype_addr):
    """One combined read covering both the 'is this really a PyTypeObject'
    check (its own ob_type == the type metaclass) and tp_name's pointer,
    since they're only 0x10 bytes apart. Returns tp_name bytes or None.

    Cached by type_ptr on the sample object: a live tree walk touches a
    handful of distinct classes (bool/int/float/NoneType/str/dict/...)
    over and over across hundreds of attributes, so after warmup this
    turns from 2 reads into a dict lookup -- the single biggest win for
    the live (round-trip-per-read) backend."""
    if not type_ptr or type_ptr & 0x7:
        return None
    cache = sample.__dict__.setdefault("_type_name_cache", {})
    if type_ptr in cache:
        return cache[type_ptr]
    chunk = sample.read_bytes(type_ptr, 0x20)
    if chunk is None or len(chunk) < 0x20:
        cache[type_ptr] = None
        return None
    ob_type, = struct.unpack_from("<Q", chunk, 8)
    if ob_type != metatype_addr:
        cache[type_ptr] = None
        return None
    tp_name_ptr, = struct.unpack_from("<Q", chunk, 0x18)
    name = sample.read_cstr(tp_name_ptr) if tp_name_ptr else None
    cache[type_ptr] = name
    return name


def looks_like_type(sample: Sample, addr, metatype_addr):
    """A valid PyTypeObject's own ob_type equals the 'type' metaclass."""
    return type_name_if_valid_type(sample, addr, metatype_addr) is not None


def classify(sample: Sample, value, metatype_addr):
    """Best-effort label for an 8-byte word found in memory."""
    if value == 0:
        return "NULL"
    chunk = sample.read_bytes(value, 0x10)
    if chunk is None:
        if value < 0x10000:
            return f"small-int? {value}"
        return None
    refcnt, type_ptr = struct.unpack("<2Q", chunk)
    name = type_name_if_valid_type(sample, type_ptr, metatype_addr)
    if name is not None:
        return f"instance of {name.decode('latin1')!r} (type@{type_ptr:#x}, refcnt={refcnt})"
    name2 = type_name_if_valid_type(sample, value, metatype_addr)
    if name2 is not None:
        return f"TYPE OBJECT {name2.decode('latin1')!r}"
    return "in-region, unrecognized"


STR_TYPE = None  # set at runtime once known


def describe_value(sample: Sample, value, metatype_addr, str_type_addr):
    if value == 0:
        return "None-ish/NULL"
    type_ptr = sample.read_u64(value + 8)
    if type_ptr == str_type_addr:
        s = sample.read_pystr(value)
        if s is not None:
            return f"str {s!r}"
    label = classify(sample, value, metatype_addr)
    return label or f"{value:#x}"


def _iter_entry_block(data, count):
    if data is None:
        return
    n = min(count, len(data) // 24)
    for h, k, v in struct.iter_unpack("<3Q", data[:n * 24]):
        if k:
            yield h, k, v


def walk_dict_entries(sample: Sample, dict_addr, metatype_addr, str_type_addr):
    """Yield (hash, key_addr, value_addr) for every non-null slot in the
    8-slot inline table (+0x38) and, if present, the external overflow
    table pointed to by +0x28. Header is 7 words / 0x38 bytes: refcnt,
    type, two duplicate count fields, capacity mask, overflow ptr, shared
    vtable ptr -- confirmed against tp_basicsize=248 = 0x38 + 8*24.

    Reads each block (inline, overflow) in a single call instead of one
    read per 24-byte slot -- matters a lot once the backend is a live
    process read rather than a local mmap, where each read is a real
    round trip."""
    header = sample.read_bytes(dict_addr, 0x38)
    if header is None:
        return
    inline = sample.read_bytes(dict_addr + 0x38, 8 * 24)
    yield from _iter_entry_block(inline, 8)
    overflow = struct.unpack_from("<Q", header, 0x28)[0]
    mask = struct.unpack_from("<Q", header, 0x20)[0]
    capacity = mask + 1 if mask and mask < (1 << 20) else 0
    if overflow and capacity:
        block = sample.read_bytes(overflow, capacity * 24)
        yield from _iter_entry_block(block, capacity)


def cmd_walkdict(args):
    s = open_backend(args)
    metatype = int(args.metatype, 0) if args.metatype else find_metatype(s, int(args.seed, 0))
    dict_addr = int(args.dict_addr, 0)
    # find str type address by locating a known-good str instance if not given
    str_type = int(args.str_type, 0) if args.str_type else None
    if str_type is None:
        str_type = bootstrap_str_type(s, dict_addr, metatype)
        print(f"# auto-detected str type: {str_type:#x}", file=sys.stderr)
    n = 0
    seen = set()
    for h, k, v in walk_dict_entries(s, dict_addr, metatype, str_type):
        if k in seen:
            continue
        seen.add(k)
        key_s = s.read_pystr(k)
        key_str = key_s.decode("utf-8", "replace") if key_s else f"<key@{k:#x}>"
        val_desc = describe_value(s, v, metatype, str_type)
        print(f"  {key_str!r}: {val_desc}")
        n += 1
    print(f"\n{n} entries", file=sys.stderr)


def get_type_name(sample: Sample, addr, metatype_addr):
    """Return the class name (bytes) of a live object, or None."""
    if not addr:
        return None
    type_ptr = sample.read_u64(addr + 8)
    return type_name_if_valid_type(sample, type_ptr, metatype_addr)


def get_dict(sample: Sample, obj_addr, metatype_addr):
    """obj_addr's +0x10 field, if it's really a 'dict'-typed object."""
    dict_ptr = sample.read_u64(obj_addr + 0x10)
    if dict_ptr and get_type_name(sample, dict_ptr, metatype_addr) == b"dict":
        return dict_ptr
    return None


def bootstrap_str_type(sample: Sample, dict_addr, metatype_addr):
    """Find the 'str' type address by reading any real key out of a dict
    (dict keys are always str objects). More robust than assuming a fixed
    slot (e.g. the first inline slot) is populated -- these are sparse
    hash tables, slot 0 being empty is common and was silently breaking
    this bootstrap step before."""
    for h, k, v in walk_dict_entries(sample, dict_addr, metatype_addr, None):
        st = sample.read_u64(k + 8)
        if st:
            return st
    return None


def dict_lookup(sample: Sample, dict_addr, key: bytes, metatype_addr, str_type_addr):
    for h, k, v in walk_dict_entries(sample, dict_addr, metatype_addr, str_type_addr):
        if sample.read_pystr(k) == key:
            return v
    return None


REPR_PATTERN = re.compile(rb'<([A-Za-z_][A-Za-z0-9_.]*) object at 0X([0-9A-F]+)')


def repr_scan(sample: Sample, class_names=None, limit=200):
    """Scan a full dump (Sample only -- needs .mm) for EVE's own debug/log
    repr text `<ClassName object at 0X...>`, which embeds live object
    addresses directly. `class_names`, if given, restricts to those
    classes; otherwise returns every hit found (bounded by `limit`).
    Returns {class_name: [addr, ...]}."""
    found = {}
    n = 0
    for m in REPR_PATTERN.finditer(sample.mm):
        cls = m.group(1).decode()
        if class_names is not None and cls not in class_names:
            continue
        found.setdefault(cls, []).append(int(m.group(2), 16))
        n += 1
        if n >= limit:
            break
    return found


def walk_to_root(sample: Sample, addr, metatype_addr, str_type_addr, max_hops=30):
    """Follow obj.__dict__['_parentRef'] (a weakref to the parent) upward
    until an object with no '_parentRef' key is reached -- that's the
    root of the UI tree (see CLAUDE.md: found this way, converges in a
    couple of hops from any live widget to the 'UIRoot'/'Desktop' object)."""
    visited = set()
    cur = addr
    for _ in range(max_hops):
        if cur in visited:
            return cur
        visited.add(cur)
        d = get_dict(sample, cur, metatype_addr)
        if d is None:
            return cur
        pref = dict_lookup(sample, d, b"_parentRef", metatype_addr, str_type_addr)
        if pref is None:
            return cur
        # A '_parentRef' key can be present but hold the interpreter's None
        # singleton rather than a real weakref (e.g. for containers that sit
        # right under the root) -- dereferencing None's address as if it were
        # a weakref reads adjacent, unrelated heap bytes as "the parent" and
        # silently walks to a bogus address. Guard by checking the value is
        # actually weakref-typed before treating +0x10 as wr_object.
        if get_type_name(sample, pref, metatype_addr) != b"weakref":
            return cur
        wr_object = sample.read_u64(pref + 0x10)
        if not wr_object:
            return cur
        cur = wr_object
    return cur


def find_ui_root(sample: Sample, metatype_addr, str_type_addr):
    """Find the UI tree's root object address in a fresh dump. Tries a
    direct repr-scan for 'UIRoot' first (seen reliably across sessions, but
    can be evicted from EVE's own debug-log ring buffer under heavy log
    volume -- e.g. a busy trade hub with hundreds of names in local chat);
    falls back to scanning for known widget classes and walking up via
    _parentRef otherwise. Some widgets (e.g. a HUD layer, or a popped-out
    inventory window) are themselves self-contained trees whose _parentRef
    walk dead-ends before reaching the real desktop root, so this tries
    every available seed and prefers a result actually named 'UIRoot',
    falling back to whichever root address the most seeds agree on.

    any_hits' limit is deliberately generous (not a small number like 50):
    repr_scan's limit counts every match, not distinct classes, and the
    debug-log ring buffer can be dominated by dozens of copies of the same
    line (e.g. repeated ModuleButton tooltip reads) -- with a small limit,
    `seeds` can end up holding only that one repeated (class, address)
    pair, so the "vote" is really just one seed's possibly-wrong result
    trivially winning unopposed. Observed live: this produced a
    Tr2Sprite2d root instead of UIRoot. A wide limit makes it far more
    likely the scan reaches enough distinct classes for the vote to mean
    something.
    """
    hits = repr_scan(sample, {"UIRoot"}, limit=5)
    if hits.get("UIRoot"):
        return hits["UIRoot"][0]
    any_hits = repr_scan(sample, limit=500)
    seeds = [addr for addrs in any_hits.values() for addr in addrs[:1]]
    if not seeds:
        return None
    votes = {}
    for seed in seeds:
        root = walk_to_root(sample, seed, metatype_addr, str_type_addr, max_hops=30)
        if root is None:
            continue
        if get_type_name(sample, root, metatype_addr) == b"UIRoot":
            return root
        votes[root] = votes.get(root, 0) + 1
    if votes:
        return max(votes, key=votes.get)
    return None


def dict_items(sample: Sample, dict_addr, metatype_addr, str_type_addr):
    """Decode every (key_str, value_addr) pair in one pass -- used instead
    of dict_lookup when a caller needs more than one key from the same
    dict, so the entries are only read once. Key strings are always
    interned identifiers (short), so their decode reads are batched into
    one round trip instead of one read_pystr call per entry -- a dict
    with 50-140 attributes previously meant that many separate round
    trips just to find out the attribute *names*."""
    triples = list(walk_dict_entries(sample, dict_addr, metatype_addr, str_type_addr))
    if not triples:
        return []
    chunks = sample.read_bytes_batch([(k + 0x10, sample._PYSTR_OPTIMISTIC_CHUNK) for _, k, _ in triples])
    items = []
    for (h, k, v), chunk in zip(triples, chunks):
        ks = parse_pystr_chunk(chunk)
        if ks is None:
            ks = sample.read_pystr(k)  # rare: key longer than the optimistic chunk
        if ks:
            items.append((ks, v))
    return items


def read_pyfloat(sample: Sample, addr):
    b = sample.read_bytes(addr + 0x10, 8)
    return struct.unpack("<d", b)[0] if b and len(b) == 8 else None


def read_pyint(sample: Sample, addr):
    """Python-2-style PyIntObject: PyObject_HEAD + a plain signed 8-byte
    ob_ival at +0x10. Fixed machine word, not arbitrary precision."""
    b = sample.read_bytes(addr + 0x10, 8)
    return struct.unpack("<q", b)[0] if b and len(b) == 8 else None


def read_pylong(sample: Sample, addr):
    """Python-2-style PyLongObject: PyObject_VAR_HEAD (refcnt, type,
    ob_size) + ob_size 30-bit digits (each stored in a 4-byte slot,
    little-endian, least-significant digit first). ob_size's sign is the
    number's sign; ob_size==0 means the value 0."""
    # optimistic combined read: ob_size (8 bytes @+0x10) plus up to 16
    # digits (64 bytes @+0x18) covers the overwhelming majority of real
    # values in one round trip; only a genuinely huge bignum needs a
    # second read.
    chunk = sample.read_bytes(addr + 0x10, 8 + 16 * 4)
    if chunk is None or len(chunk) < 8:
        return None
    ob_size = struct.unpack_from("<q", chunk, 0)[0]
    if ob_size == 0:
        return 0
    ndigits = abs(ob_size)
    if ndigits > 64:  # sanity cap; a legit small int shouldn't need this many
        return None
    if 8 + 4 * ndigits <= len(chunk):
        data = chunk[8:8 + 4 * ndigits]
    else:
        data = sample.read_bytes(addr + 0x18, 4 * ndigits)
    if data is None or len(data) < 4 * ndigits:
        return None
    digits = struct.unpack(f"<{ndigits}I", data)
    value = 0
    for i, d in enumerate(digits):
        value += d * (2 ** 30) ** i
    return -value if ob_size < 0 else value


def read_pyunicode(sample: Sample, addr):
    """Python-2-style PyUnicodeObject: PyObject_HEAD + length (+0x10) +
    a pointer to an externally-allocated UCS-4 buffer (+0x18) + hash
    (+0x20). Not inline like the compact-ASCII 'str' object."""
    hdr = sample.read_bytes(addr + 0x10, 16)
    if hdr is None or len(hdr) < 16:
        return None
    length, buf_ptr = struct.unpack("<2Q", hdr)
    if length > 65536:
        return None
    data = sample.read_bytes(buf_ptr, length * 4)
    if data is None or len(data) < length * 4:
        return None
    return data.decode("utf-32-le", errors="replace")


def decode_simple_scalar(sample: Sample, value, tname, raw):
    """Parse a value already fetched by build_tree's batched read (a
    single MemoryReaderBase._PYSTR_OPTIMISTIC_CHUNK-or-8-byte chunk at
    value+0x10) for the common scalar kinds. Falls back to a normal
    (unbatched) read only for the rare case of a string longer than the
    optimistic chunk -- everything else this function handles is exactly
    one fixed-size field, always fully covered by the pre-fetched chunk."""
    if tname == b"str":
        s = parse_pystr_chunk(raw)
        if s is None:
            s = sample.read_pystr(value)
        return s.decode("utf-8", "replace") if s is not None else None
    if tname == b"float":
        return struct.unpack("<d", raw)[0] if raw and len(raw) == 8 else None
    if tname == b"bool":
        v = struct.unpack("<q", raw)[0] if raw and len(raw) == 8 else None
        return bool(v) if v is not None else None
    if tname == b"int":
        return struct.unpack("<q", raw)[0] if raw and len(raw) == 8 else None
    return None


def decode_pycolor(sample: Sample, addr, metatype_addr, str_type_addr):
    """PyColor: an ordinary widget-shaped object (dict at +0x10) whose own
    __dict__ holds `_r`/`_g`/`_b`/`_a` floats in [0, 1]. Overview-entry
    hostility detection (iconSpriteHasColorOfRat in the EVE bots) reads
    this via a `_color` attribute decoded as {aPercent, rPercent,
    gPercent, bPercent} -- confirmed live against a real NPC overview
    icon's `_color` value before trusting this shape. Returns None if the
    expected fields aren't all present (never guess a color)."""
    d = get_dict(sample, addr, metatype_addr)
    if d is None:
        return None
    comps = {}
    for h, k, v in walk_dict_entries(sample, d, metatype_addr, str_type_addr):
        ks = sample.read_pystr(k)
        if ks in (b"_r", b"_g", b"_b", b"_a") and ks not in comps:
            fv = read_pyfloat(sample, v)
            if fv is not None:
                comps[ks] = fv
    if not all(k in comps for k in (b"_r", b"_g", b"_b", b"_a")):
        return None
    return {
        "aPercent": round(comps[b"_a"] * 100),
        "rPercent": round(comps[b"_r"] * 100),
        "gPercent": round(comps[b"_g"] * 100),
        "bPercent": round(comps[b"_b"] * 100),
    }


def decode_link(sample: Sample, addr, metatype_addr, str_type_addr):
    """Link: a rich-text hyperlink object (e.g. a solar-system-name label's
    `_setText`, matching the exact gap documented in this project's own
    Elm decoder comment: '_setText contained not string but a python
    object of type Link, which in turn references a dictionary. That
    dictionary contains a key _text with the actual text.'). Unlike
    PyColor, Link's own dict pointer is NOT at the usual +0x10 (that
    slot holds an unrelated small int, confirmed live -- looked like a
    handle/index similar to the very first thin-wrapper classes this
    project ever decoded); tp_basicsize is 64 bytes (double the
    standard 32-byte wrapper) and the real dict sits at +0x30. Found by
    dumping a live instance whole and testing each word for the
    type-metaclass invariant. Returns None if no `_text` key is found
    (never guess a string)."""
    dict_ptr = sample.read_u64(addr + 0x30)
    if not dict_ptr or get_type_name(sample, dict_ptr, metatype_addr) != b"dict":
        return None
    for h, k, v in walk_dict_entries(sample, dict_ptr, metatype_addr, str_type_addr):
        if sample.read_pystr(k) == b"_text" and v:
            return describe_primitive(sample, v, metatype_addr, str_type_addr)
    return None


def describe_primitive(sample: Sample, value, metatype_addr, str_type_addr, tname=_UNSET):
    """Decode simple scalar values for dictEntriesOfInterest; return None
    for anything not worth inlining (nested objects, containers, etc).
    `tname` can be supplied precomputed (e.g. from a batched fetch across
    a whole dict's worth of attributes at once) to skip re-deriving it
    here; omit it to have this function look it up itself."""
    if value == 0:
        return None
    if tname is _UNSET:
        tname = get_type_name(sample, value, metatype_addr)
    if tname == b"str":
        s = sample.read_pystr(value)
        return s.decode("utf-8", "replace") if s is not None else None
    if tname == b"float":
        return read_pyfloat(sample, value)
    if tname == b"NoneType":
        return None
    if tname == b"bool":
        v = read_pyint(sample, value)
        return bool(v) if v is not None else None
    if tname == b"int":
        return read_pyint(sample, value)
    if tname == b"long":
        return read_pylong(sample, value)
    if tname == b"unicode":
        return read_pyunicode(sample, value)
    if tname == b"PyColor":
        return decode_pycolor(sample, value, metatype_addr, str_type_addr)
    if tname == b"Link":
        return decode_link(sample, value, metatype_addr, str_type_addr)
    return None  # nested instances/containers: omit from dictEntriesOfInterest


def get_children_addrs_from_wrapper(sample: Sample, children_wrapper, metatype_addr, str_type_addr):
    """Second half of the children recipe, given obj.__dict__['children']
    (a PyChildrenList) already in hand: .__dict__['_childrenObjects'] ->
    stock CPython list -> ob_item array. Split out from
    get_children_addrs so build_tree can supply the wrapper from a dict
    walk it already did, instead of re-walking obj's dict from scratch
    just to find the 'children' key again."""
    if not children_wrapper:
        return []
    pcl_dict = get_dict(sample, children_wrapper, metatype_addr)
    if pcl_dict is None:
        return []
    # dict_items (batched key-name decode, one round trip for the whole
    # entry table's keys) instead of dict_lookup (decodes each candidate
    # key name with its own unbatched round trip) -- this dict is small
    # (PyChildrenList's own bookkeeping, not the tree's big per-widget
    # attribute dicts) but every single node in the tree pays for this
    # lookup once, so an unbatched scan here was a real, avoidable cost
    # multiplied by the whole tree's node count.
    child_objs_list = None
    for key_s, v in dict_items(sample, pcl_dict, metatype_addr, str_type_addr):
        if key_s == b"_childrenObjects":
            child_objs_list = v
            break
    if not child_objs_list or get_type_name(sample, child_objs_list, metatype_addr) != b"list":
        return []
    hdr = sample.read_bytes(child_objs_list, 40)
    if hdr is None or len(hdr) < 40:
        return []
    _refcnt, _type, ob_size, ob_item, _allocated = struct.unpack("<5Q", hdr)
    items = sample.read_bytes(ob_item, 8 * ob_size)
    if items is None:
        return []
    return list(struct.unpack(f"<{ob_size}Q", items))


def _batch_dict_walk(sample, dict_ptr_candidates_by_addr, metatype_addr):
    """Shared engine for both node-attribute dicts and PyChildrenList's
    small bookkeeping dict: given {addr: dict_ptr_candidate}, batch-verify
    each is really 'dict'-typed, batch-fetch headers/inline/overflow
    blocks, and return {addr: [(key_addr, value_addr), ...]} -- all in a
    handful of round trips covering every address at once, not one round
    trip per address. Pure bytes-in/structure-out; no key-name decoding
    here (callers batch that separately, since what they're looking for
    differs: node attributes want everything, the children-wrapper walk
    only wants '_childrenObjects')."""
    addrs = list(dict_ptr_candidates_by_addr.keys())
    type_raw = sample.read_bytes_batch(
        [(dict_ptr_candidates_by_addr[a] + 8, 8) if dict_ptr_candidates_by_addr[a] else (0, 0) for a in addrs]
    )
    real_dict_ptr = {}
    for addr, raw in zip(addrs, type_raw):
        dp = dict_ptr_candidates_by_addr[addr]
        if not dp:
            continue
        tp = struct.unpack("<Q", raw)[0] if raw and len(raw) == 8 else None
        if type_name_if_valid_type(sample, tp, metatype_addr) == b"dict":
            real_dict_ptr[addr] = dp

    dict_addrs = list(real_dict_ptr.values())
    headers = dict(zip(dict_addrs, sample.read_bytes_batch([(dp, 0x38) for dp in dict_addrs])))
    inline_blocks = dict(zip(dict_addrs, sample.read_bytes_batch([(dp + 0x38, 8 * 24) for dp in dict_addrs])))

    overflow_reqs, overflow_order = [], []
    capacity_of = {}
    for dp in dict_addrs:
        header = headers.get(dp)
        if not header or len(header) < 0x38:
            continue
        overflow_ptr = struct.unpack_from("<Q", header, 0x28)[0]
        mask = struct.unpack_from("<Q", header, 0x20)[0]
        capacity = mask + 1 if mask and mask < (1 << 20) else 0
        capacity_of[dp] = capacity
        if overflow_ptr and capacity:
            overflow_reqs.append((overflow_ptr, capacity * 24))
            overflow_order.append(dp)
    overflow_blocks = dict(zip(overflow_order, sample.read_bytes_batch(overflow_reqs) if overflow_reqs else []))

    entries_by_addr = {}
    for addr in addrs:
        dp = real_dict_ptr.get(addr)
        if dp is None:
            entries_by_addr[addr] = []
            continue
        triples = list(_iter_entry_block(inline_blocks.get(dp), 8))
        if dp in overflow_blocks:
            triples += list(_iter_entry_block(overflow_blocks[dp], capacity_of.get(dp, 0)))
        entries_by_addr[addr] = [(k, v) for h, k, v in triples]
    return entries_by_addr


def _batch_decode_keys(sample, entries_by_addr):
    """Batch-fetch and decode every key string across every addr's entry
    list in one round trip (falling back to a real read only for the
    rare oversized key). Returns {addr: [(key_bytes_or_None, value_addr), ...]}
    in the same order as the input entries."""
    reqs, owners = [], []
    for addr, entries in entries_by_addr.items():
        for idx, (k, v) in enumerate(entries):
            reqs.append((k + 0x10, MemoryReaderBase._PYSTR_OPTIMISTIC_CHUNK))
            owners.append((addr, idx))
    raw = sample.read_bytes_batch(reqs) if reqs else []
    decoded = {}
    for (addr, idx), r in zip(owners, raw):
        k, v = entries_by_addr[addr][idx]
        ks = parse_pystr_chunk(r)
        if ks is None:
            ks = sample.read_pystr(k)  # rare fallback: key longer than the optimistic chunk
        decoded[(addr, idx)] = ks

    out = {}
    for addr, entries in entries_by_addr.items():
        out[addr] = [(decoded.get((addr, idx)), v) for idx, (k, v) in enumerate(entries)]
    return out


def build_tree(sample: Sample, root_addr, metatype_addr, str_type_addr, max_depth=6, max_nodes=500):
    """Breadth-first, level-batched UI tree walk -- same UITreeNode JSON
    output as the original per-node depth-first version, but processes
    one tree LEVEL at a time, batching every node at that level's reads
    together instead of paying ~14 round trips per node individually.

    Found necessary once a real, densely populated live tree (2664+
    nodes on the machine this was developed on) made the old approach
    take 3+ seconds for a single read -- see CLAUDE.md. Cross-checked
    against the old implementation's output on the file-backed Sample
    backend (round-trip count doesn't affect that backend's output, so
    it's an exact-match oracle) before trusting this on the live path.

    Note: the node budget (max_nodes) is applied by truncating each
    LEVEL to the remaining budget, not by a strict global visitation
    order like the old depth-first version -- if a cap is hit mid-level,
    which specific nodes get included can differ slightly from the old
    ordering. This is an intentional, acceptable difference (the cap's
    purpose is bounding total work, not guaranteeing a specific
    truncation order), not a bug."""
    nodes = {}
    child_addrs_of = {}
    current_level = [root_addr]
    depth = 0
    total = 0

    while current_level and depth <= max_depth and total < max_nodes:
        remaining = max_nodes - total
        if len(current_level) > remaining:
            current_level = current_level[:remaining]
        total += len(current_level)

        # [type_ptr, dict_ptr] are adjacent (obj+8, obj+0x10) -- one 16-byte
        # read per node covers both fields in a single batched round trip.
        combined = sample.read_bytes_batch([(addr + 8, 16) for addr in current_level])
        type_ptrs, dict_ptr_candidates = {}, {}
        for addr, raw in zip(current_level, combined):
            if raw and len(raw) == 16:
                tp, dp = struct.unpack("<QQ", raw)
            else:
                tp, dp = None, None
            type_ptrs[addr] = tp
            dict_ptr_candidates[addr] = dp
        tnames = {addr: type_name_if_valid_type(sample, type_ptrs[addr], metatype_addr) for addr in current_level}

        entries_by_addr = _batch_dict_walk(sample, dict_ptr_candidates, metatype_addr)
        keyed_entries = _batch_decode_keys(sample, entries_by_addr)

        node_attrs, node_children_wrapper = {}, {}
        for addr in current_level:
            # The custom dict's inline block and overflow block can hold
            # genuine duplicate keys with *different* values (a known,
            # unexplained oddity -- see CLAUDE.md, "possibly a small
            # recently-touched cache vs the authoritative backing
            # store"). Matching the original per-node implementation's
            # behavior exactly, since which copy is "correct" is
            # genuinely unresolved and this isn't the place to guess a
            # new policy: attribute values use last-occurrence-wins
            # (walk order is inline-then-overflow, so overflow wins on a
            # duplicate -- the old code's dict-assignment loop did this
            # by construction, one key at a time overwriting), while
            # 'children' uses first-occurrence-wins (the old code found
            # it via `next(...)` over the entries, i.e. the first match).
            attrs_dict, children_wrapper = {}, None
            for ks, v in keyed_entries.get(addr, []):
                if not ks:
                    continue
                if ks == b"children":
                    if children_wrapper is None:
                        children_wrapper = v
                elif v:
                    attrs_dict[ks] = v
            node_attrs[addr] = list(attrs_dict.items())
            node_children_wrapper[addr] = children_wrapper

        # Attribute VALUE type lookups and scalar decodes, batched across
        # every attribute of every node in this level at once.
        flat_reqs, flat_owner = [], []
        for addr in current_level:
            for i, (ks, v) in enumerate(node_attrs[addr]):
                flat_reqs.append((v + 8, 8))
                flat_owner.append((addr, i))
        attr_type_raw = sample.read_bytes_batch(flat_reqs) if flat_reqs else []
        attr_tnames = {}
        for (addr, i), raw in zip(flat_owner, attr_type_raw):
            tp = struct.unpack("<Q", raw)[0] if raw and len(raw) == 8 else None
            attr_tnames[(addr, i)] = type_name_if_valid_type(sample, tp, metatype_addr)

        SIMPLE_KINDS = {b"str": MemoryReaderBase._PYSTR_OPTIMISTIC_CHUNK,
                        b"int": 8, b"bool": 8, b"float": 8}
        simple_reqs, simple_owner = [], []
        for addr in current_level:
            for i, (ks, v) in enumerate(node_attrs[addr]):
                tn = attr_tnames.get((addr, i))
                if tn in SIMPLE_KINDS:
                    simple_reqs.append((v + 0x10, SIMPLE_KINDS[tn]))
                    simple_owner.append((addr, i))
        simple_raw = sample.read_bytes_batch(simple_reqs) if simple_reqs else []
        simple_by_owner = dict(zip(simple_owner, simple_raw))

        for addr in current_level:
            entries_dict = {}
            for i, (ks, v) in enumerate(node_attrs[addr]):
                tn = attr_tnames.get((addr, i))
                if (addr, i) in simple_by_owner:
                    prim = decode_simple_scalar(sample, v, tn, simple_by_owner[(addr, i)])
                else:
                    prim = describe_primitive(sample, v, metatype_addr, str_type_addr, tname=tn)
                if prim is not None:
                    entries_dict[ks.decode("utf-8", "replace")] = prim
            nodes[addr] = {
                "pythonObjectAddress": f"{addr:#x}",
                "pythonObjectTypeName": tnames[addr].decode("latin1") if tnames.get(addr) else None,
                "dictEntriesOfInterest": entries_dict,
                "children": [],
            }

        # Children resolution: obj.__dict__['children'] (a PyChildrenList,
        # already found above) -> its own __dict__['_childrenObjects'] ->
        # a stock CPython list -> ob_item array. Batched across every node
        # in this level that has a children_wrapper, same pattern as above.
        next_level = []
        if depth < max_depth:
            wrapper_addrs = [addr for addr in current_level if node_children_wrapper.get(addr)]
            w_combined = sample.read_bytes_batch(
                [(node_children_wrapper[addr] + 8, 16) for addr in wrapper_addrs]
            )
            w_dict_ptr = {}
            for addr, raw in zip(wrapper_addrs, w_combined):
                if raw and len(raw) == 16:
                    _tp, dp = struct.unpack("<QQ", raw)
                else:
                    dp = None
                w_dict_ptr[addr] = dp

            w_entries = _batch_dict_walk(sample, w_dict_ptr, metatype_addr)
            w_keyed = _batch_decode_keys(sample, w_entries)

            child_objs_list_addr = {}
            for addr in wrapper_addrs:
                for ks, v in w_keyed.get(addr, []):
                    if ks == b"_childrenObjects":
                        child_objs_list_addr[addr] = v
                        break

            list_addrs = list(child_objs_list_addr.values())
            list_type_raw = sample.read_bytes_batch([(la + 8, 8) for la in list_addrs])
            header_reqs, header_owner = [], []
            for la, raw in zip(list_addrs, list_type_raw):
                tp = struct.unpack("<Q", raw)[0] if raw and len(raw) == 8 else None
                if type_name_if_valid_type(sample, tp, metatype_addr) == b"list":
                    header_reqs.append((la, 40))
                    header_owner.append(la)
            header_raw = sample.read_bytes_batch(header_reqs) if header_reqs else []

            item_reqs, item_owner, list_sizes = [], [], {}
            for la, raw in zip(header_owner, header_raw):
                if not raw or len(raw) < 40:
                    continue
                _refcnt, _type, ob_size, ob_item, _allocated = struct.unpack("<5Q", raw)
                list_sizes[la] = ob_size
                item_reqs.append((ob_item, 8 * ob_size))
                item_owner.append(la)
            item_raw = sample.read_bytes_batch(item_reqs) if item_reqs else []
            list_items = {}
            for la, raw in zip(item_owner, item_raw):
                n = list_sizes[la]
                list_items[la] = list(struct.unpack(f"<{n}Q", raw)) if raw and len(raw) == 8 * n else []

            for addr in current_level:
                la = child_objs_list_addr.get(addr)
                children = list_items.get(la, []) if la else []
                child_addrs_of[addr] = children
                next_level.extend(children)

        current_level = next_level
        depth += 1

    def assemble(addr, seen):
        if addr in seen or addr not in nodes:
            return None
        seen = seen | {addr}
        node = nodes[addr]
        node["children"] = [c for c in
                             (assemble(a, seen) for a in child_addrs_of.get(addr, []) if a in nodes)
                             if c is not None]
        return node

    return assemble(root_addr, set())


def open_backend(args):
    if args.live_pid:
        return LiveSample(args.live_pid)
    if not args.sample_dir:
        print("need either a sample_dir or --live-pid", file=sys.stderr)
        sys.exit(1)
    return Sample(args.sample_dir)


def cmd_tree(args):
    import json
    import time
    s = open_backend(args)
    t0 = time.monotonic()
    metatype = int(args.metatype, 0) if args.metatype else find_metatype(s, int(args.addr, 0))
    root_addr = int(args.addr, 0)
    d = get_dict(s, root_addr, metatype)
    if d is None:
        print("root object has no dict; can't bootstrap str type", file=sys.stderr)
        return
    str_type = bootstrap_str_type(s, d, metatype)
    tree = build_tree(s, root_addr, metatype, str_type,
                       max_depth=args.max_depth, max_nodes=args.max_nodes)
    elapsed = time.monotonic() - t0
    print(json.dumps(tree, indent=2))
    if isinstance(s, LiveSample):
        print(f"# elapsed={elapsed:.3f}s round_trips={s.round_trips} reads={s.reads} bytes_read={s.bytes_read}", file=sys.stderr)
        s.close()
    else:
        print(f"# elapsed={elapsed:.3f}s", file=sys.stderr)


def find_metatype(sample: Sample, seed_addr):
    """Given any known instance address, walk to its type, then that type's
    own ob_type -- in CPython, type(type) is type, so this converges."""
    t = sample.read_u64(seed_addr + 8)
    if t is None:
        return None
    tt = sample.read_u64(t + 8)
    return tt


def cmd_dump(args):
    s = open_backend(args)
    metatype = args.metatype and int(args.metatype, 0)
    if metatype is None and args.seed:
        metatype = find_metatype(s, int(args.seed, 0))
        print(f"# auto-detected metatype candidate: {metatype:#x}", file=sys.stderr)
    addr = int(args.addr, 0)
    n = args.length
    data = s.read_bytes(addr, n)
    if data is None:
        print("address not in any dumped region")
        return
    for i in range(0, len(data) - 7, 8):
        word = struct.unpack_from("<Q", data, i)[0]
        label = classify(s, word, metatype) if metatype else ""
        print(f"  +{i:#04x} ({addr+i:#x}): {word:#018x}  {label or ''}")


def cmd_find(args):
    s = Sample(args.sample_dir)
    for needle_str in args.needles:
        needle = needle_str.encode()
        offs = s.find_all(needle, limit=args.limit)
        print(f"\n=== {needle_str!r} ({len(needle)} bytes) -- {len(offs)} occurrence(s) ===")
        for off in offs:
            addr = None
            for a, bw, o in s.regions:
                if o <= off < o + bw:
                    addr = a + (off - o)
                    break
            addr_s = f"{addr:#x}" if addr is not None else "NONE"
            print(f"  dump_offset={off:#x} vaddr={addr_s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", dest="sample_dir", help="memory_sample output dir")
    ap.add_argument("--live-pid", type=int, help="read the live process directly via live_reader instead of a dump")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="dump bytes at an address, classifying pointer-shaped words")
    d.add_argument("addr", help="hex address, e.g. 0x358051470")
    d.add_argument("--length", type=int, default=256)
    d.add_argument("--metatype", help="known 'type' metaclass address (hex)")
    d.add_argument("--seed", help="any known instance address to auto-derive the metatype from")
    d.set_defaults(func=cmd_dump)

    fnd = sub.add_parser("find", help="find byte string occurrences and their addresses")
    fnd.add_argument("needles", nargs="+")
    fnd.add_argument("--limit", type=int, default=20)
    fnd.set_defaults(func=cmd_find)

    wd = sub.add_parser("walkdict", help="walk a custom-dict object's (hash,key,value) entries")
    wd.add_argument("dict_addr", help="hex address of the dict object (an instance's +0x10 field)")
    wd.add_argument("--metatype", help="known 'type' metaclass address (hex)")
    wd.add_argument("--seed", help="any known instance address to auto-derive the metatype from")
    wd.add_argument("--str-type", help="known 'str' type address (hex); auto-detected if omitted")
    wd.set_defaults(func=cmd_walkdict)

    tr = sub.add_parser("tree", help="recursively walk a widget's UI tree, emit UITreeNode-shaped JSON")
    tr.add_argument("addr", help="hex address of the root widget instance")
    tr.add_argument("--metatype", help="known 'type' metaclass address (hex); auto-detected from addr if omitted")
    tr.add_argument("--max-depth", type=int, default=6)
    tr.add_argument("--max-nodes", type=int, default=500)
    tr.set_defaults(func=cmd_tree)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
