"""Windows memory reader for the EVE Online client, and the CPython 2.7 decoders
built on it.

This is the Windows counterpart of ``tools/macos-host/re_helper.py``: the reader
and the struct decoding, in one importable module, usable against a live process.
Where ``re_helper`` calls ``mach_vm_read_overwrite`` through ``live_reader``, this
calls ``ReadProcessMemory`` directly through ``ctypes``.

Two things here are deliberately different from the macOS side, and both are
consequences of what the platform offers rather than preferences.

**Struct offsets are a parameter, not a constant.**  ``tools/macos-host``
hardcodes ``0x10``/``0x18``/``0x20``/``0x24`` because they were reverse-engineered
once from one build.  Issue #176 names transferring those to a different binary as
"unknown and the whole question", and the failure it warns about -- a reader that
decodes wrongly and produces plausible nonsense rather than an error -- is exactly
what a hardcoded guess produces.  So ``Layout`` carries them, ``probe.py`` derives
them from the running client, and every decoder takes the layout it was given.

**Types are named from ``python27.dll``'s export table, not from a heuristic.**
The macOS client is a single statically linked binary, so ``re_helper`` has to
bootstrap the ``type`` metaclass by scanning for the ``type(type) is type``
invariant and validating candidates.  The Windows client loads a real
``python27.dll``, which *exports* ``PyType_Type``, ``PyString_Type``,
``PyInt_Type`` and the rest as data symbols.  Reading its export directory out of
the target's own memory gives those addresses authoritatively, which removes the
bootstrap, its stale-seed trap (CLAUDE.md: "hit in three separate tools"), and the
whole-address-space scan the 2019 C# reader needed to find the metaclass.
"""

from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Iterator, Optional

# --------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

# Protections that permit a read at all.  A PAGE_GUARD page raises on access even
# for the owning process, and reading one would arm the guard as a side effect, so
# it is excluded rather than merely expected to fail.
READABLE_PROTECT = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}  # R, RW, WC, XR, XRW, XWC


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wintypes.DWORD),
        ("__alignment1", wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("__alignment2", wintypes.DWORD),
    ]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE

_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL

_k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
_k32.ReadProcessMemory.restype = wintypes.BOOL

_k32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION64),
    ctypes.c_size_t,
]
_k32.VirtualQueryEx.restype = ctypes.c_size_t


class MemoryReadError(RuntimeError):
    pass


class AttachFailed(RuntimeError):
    """OpenProcess was refused.

    Issue #176 lists "whether ReadProcessMemory against the EVE client is
    permitted under current Windows protections and whatever anti-cheat the
    client ships" as unverified.  This is the exception that answers it, and it
    carries the Win32 error so that the three interesting refusals are
    distinguishable: 5 (ACCESS_DENIED, a privilege or an object-callback strip),
    87 (INVALID_PARAMETER, no such pid), 299 (PARTIAL_COPY, which is a *read*
    failure and cannot appear here).
    """


# --------------------------------------------------------------------------
# Struct layout
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    """CPython 2.7 struct offsets for one build.

    The defaults are the LP64 layout ``tools/macos-host`` records, which is what
    stock CPython 2.7 compiles to wherever ``Py_ssize_t`` and every pointer are
    8 bytes.  Windows x64 is LLP64 rather than LP64, and the difference is not
    cosmetic: ``long`` is 4 bytes there and 8 here, so any field declared ``long``
    moves.  In CPython 2.7 that is ``PyIntObject.ob_ival`` and
    ``PyStringObject.ob_shash`` -- the integer's whole value, and the offset the
    string's characters start at.  ``probe.py`` measures both rather than
    assuming either, and ``windows_x64_stock()`` below is the LLP64 prediction to
    measure against.
    """

    # PyObject header
    ob_type: int = 0x08
    # PyVarObject
    ob_size: int = 0x10
    # PyTypeObject
    tp_name: int = 0x18
    # PyStringObject (Python 2 str): header + ob_size + ob_shash + ob_sstate + chars
    str_shash: int = 0x18
    str_chars: int = 0x24
    # PyIntObject
    int_value: int = 0x10
    int_value_size: int = 8
    # PyLongObject: ob_size is the digit count and sign; digits follow
    long_digits: int = 0x18
    # PyUnicodeObject (Python 2 unicode): length, then a pointer to a character
    # buffer whose element width is a *build option* rather than a platform
    # constant. `Py_UNICODE` is `wchar_t`, so a CPython 2.7 configured
    # `--enable-unicode=ucs4` stores 4 bytes per character and the stock Windows
    # build stores 2. macOS reads UCS-4; this client is UCS-2.
    #
    # Getting it wrong is not a garbled string, which is why it went unnoticed
    # for a while: decoding UTF-16 bytes as UTF-32 lands on unassigned planes and
    # raises, so every `unicode` value in the tree was dropped rather than
    # mangled. Failing safe made it invisible -- the tree looked complete because
    # `str` values decoded fine, and only the values EVE happens to store as
    # `unicode` went missing. Those include every context-menu entry's text,
    # which is what a cascade matches `'jump'` against.
    unicode_length: int = 0x10
    unicode_buffer: int = 0x18
    unicode_char_size: int = 4
    # PyFloatObject
    float_value: int = 0x10
    # PyListObject
    list_items: int = 0x18
    # Blue widget wrapper: header + dict pointer + weakref slot
    widget_dict: int = 0x10
    # Blue custom dict (not a stock PyDictObject)
    dict_header: int = 0x38
    dict_mask: int = 0x20
    dict_overflow: int = 0x28
    dict_entry_size: int = 0x18
    dict_inline_entries: int = 8
    # PyWeakReference
    weakref_object: int = 0x10

    @staticmethod
    def windows_x64_stock() -> "Layout":
        """The LLP64 prediction: every ``long`` field is 4 bytes wide.

        ``PyStringObject`` is ``PyObject_VAR_HEAD; long ob_shash; int ob_sstate;
        char ob_sval[1]``.  With an 8-byte ``ob_shash`` the characters land at
        0x24 (macOS); with a 4-byte one they land at 0x20 and nothing pads them
        back out, because ``ob_sstate`` is an ``int`` either way and fills the
        gap.  ``PyIntObject.ob_ival`` is a bare ``long``, so it is 4 bytes here
        and 8 there.

        This is a prediction and not a finding.  ``probe.py`` decides between
        this and the default by reading strings whose contents are known.
        """
        return Layout(str_chars=0x20, int_value_size=4)


# --------------------------------------------------------------------------
# The reader
# --------------------------------------------------------------------------


@dataclass
class Region:
    base: int
    size: int
    protect: int

    @property
    def end(self) -> int:
        return self.base + self.size


class ProcessReader:
    """A read-only handle on another process.

    Opened with ``PROCESS_VM_READ | PROCESS_QUERY_INFORMATION`` and nothing else:
    the whole host needs to read memory and enumerate regions, and asking for
    ``PROCESS_ALL_ACCESS`` would be a broader right than the work requires
    against a live game client.
    """

    def __init__(self, pid: int):
        self.pid = pid
        handle = _k32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not handle:
            err = ctypes.get_last_error()
            raise AttachFailed(
                f"OpenProcess({pid}) failed with Win32 error {err} "
                f"({ctypes.FormatError(err).strip()})"
            )
        self._handle = handle
        self._page_cache: dict[int, bytes] = {}
        self._region_memo: list[tuple[int, int]] = []
        self._cache_enabled = False
        self.reads = 0
        self.bytes_read = 0

    def close(self) -> None:
        if self._handle:
            _k32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "ProcessReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- raw reads ---------------------------------------------------------

    def try_read(self, address: int, size: int) -> Optional[bytes]:
        """Read ``size`` bytes, or ``None`` if the read did not complete.

        A partial read is reported as a failure rather than as short data.
        ``ReadProcessMemory`` returns ERROR_PARTIAL_COPY when the range crosses
        out of a mapped region, and the bytes it did copy are real -- but a
        decoder handed a truncated struct produces a plausible wrong answer,
        which is the failure shape this whole port is being careful about.
        Callers that genuinely want the readable prefix ask for less.
        """
        if address <= 0 or size <= 0:
            return None
        buf = (ctypes.c_char * size)()
        got = ctypes.c_size_t(0)
        ok = _k32.ReadProcessMemory(
            self._handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got)
        )
        self.reads += 1
        if not ok or got.value != size:
            return None
        self.bytes_read += size
        return bytes(buf)

    def read(self, address: int, size: int) -> bytes:
        data = self.try_read(address, size)
        if data is None:
            err = ctypes.get_last_error()
            raise MemoryReadError(
                f"read of {size} bytes at 0x{address:X} failed (Win32 error {err})"
            )
        return data

    # -- page cache --------------------------------------------------------
    #
    # The macOS host added this and measured 3.36s -> 0.39s on the same tree,
    # because an object's header, its dict and that dict's entries sit within a
    # page or two of each other.  The same locality holds here.  Scoped to one
    # request for the same reason CLAUDE.md gives: holding pages across reads
    # would hand the bot a tree blended from moments seconds apart.

    # macOS uses 4K because `mach_vm_read_overwrite` is priced per call and a
    # page is its natural unit.  `ReadProcessMemory` will return any size, so the
    # block looked like a tunable here -- and measuring it says take 4K anyway,
    # for a reason worth writing down because it points the wrong way from
    # intuition.  Over one real tree:
    #
    #     block   median   RPM calls   MiB read
    #      4 KiB    2418s*     10721       41.9
    #      8 KiB    2561       8204       56.8
    #     32 KiB    4043      15463       98.0
    #     64 KiB    6606     111737      127.2
    #    128 KiB   10991     240548      161.8      (* milliseconds)
    #
    # Past 8 KiB the *call count* rises, which is the opposite of what a cache
    # is for.  `ReadProcessMemory` is all-or-nothing: a block that straddles the
    # end of a mapped region fails entirely rather than returning its readable
    # prefix, and falls back to an uncached direct read.  The client's object
    # heap is many modest regions rather than a few large ones, so the bigger the
    # block the more often it straddles one -- and each straddle costs a wasted
    # read plus an uncached one.  Bigger blocks buy locality and pay for it in
    # boundaries, and the boundaries win here.
    PAGE = 0x1000

    def begin_request(self) -> None:
        self._page_cache.clear()
        self._cache_enabled = True

    def end_request(self) -> None:
        self._page_cache.clear()
        self._cache_enabled = False

    def read_cached(self, address: int, size: int) -> Optional[bytes]:
        """Serve from a per-request 4 KiB page cache.

        Two things were tried to beat this and both lost, so they are recorded
        rather than left for the next person to retry:

        - **Bigger fixed blocks.** Call count *rose* (10,721 -> 111,737 at 64 KiB)
          because `ReadProcessMemory` is all-or-nothing and a block crossing the
          end of a mapped region fails entirely, falling back to an uncached read.
        - **Bigger blocks clipped to the containing region**, which removes that
          failure. It removes the straddling and still loses: the cost of a read
          scales with bytes copied, so 256 KiB blocks moved 1.6 GB per walk and
          took 5.8s against 2.0s. Clipped and swept, 4 KiB is still the floor
          (3.0s at 4 KiB, 4.1s at 128 KiB), and the region lookup itself costs
          more than it saves.

        What is left is not a caching problem. See `ProcessReader.call_overhead`.
        """
        if not self._cache_enabled:
            return self.try_read(address, size)
        # Fast path: the read lies inside one page, which is nearly every read a
        # walk makes -- 8 bytes of a pointer field. Worth separating because this
        # function is called ~372,000 times per tree and the general path below
        # builds a bytearray and concatenates into it for no reason when there is
        # only one page to take a slice of.
        page = address & ~(self.PAGE - 1)
        offset = address - page
        if offset + size <= self.PAGE:
            data = self._page_cache.get(page)
            if data is None:
                data = self.try_read(page, self.PAGE)
                if data is None:
                    return self.try_read(address, size)
                self._page_cache[page] = data
            return data[offset : offset + size]
        first = page
        last = (address + size - 1) & ~(self.PAGE - 1)
        out = bytearray()
        page = first
        while page <= last:
            data = self._page_cache.get(page)
            if data is None:
                data = self.try_read(page, self.PAGE)
                if data is None:
                    # The last page of a mapped region fails as a page while the
                    # bytes asked for are fine.  macOS hit this too; fall back to
                    # a direct read rather than reporting the field unreadable.
                    return self.try_read(address, size)
                self._page_cache[page] = data
            out += data
            page += self.PAGE
        start = address - first
        return bytes(out[start : start + size])

    def call_overhead(self, samples: int = 2000) -> tuple[float, float]:
        """(seconds per 8-byte read, seconds per 4 KiB read), measured.

        The number that decides whether this host wants a native helper. A walk
        makes ~10,000 reads and spends ~1.9s doing it; if that is the *syscall*
        it is a platform floor, and if it is `ctypes` marshalling it is an
        implementation one that C removes.
        """
        import time as _t

        address = self.pid and 0
        base = None
        for region in self.regions():
            if region.size >= (1 << 20):
                base = region.base
                break
        if base is None:
            return (0.0, 0.0)
        started = _t.perf_counter()
        for i in range(samples):
            self.try_read(base + (i % 64) * 8, 8)
        small = (_t.perf_counter() - started) / samples
        started = _t.perf_counter()
        for i in range(samples // 10):
            self.try_read(base + (i % 16) * 0x1000, 0x1000)
        big = (_t.perf_counter() - started) / max(1, samples // 10)
        return (small, big)

    # -- typed reads -------------------------------------------------------

    def u64(self, address: int) -> Optional[int]:
        data = self.read_cached(address, 8)
        return None if data is None else struct.unpack("<Q", data)[0]

    def i64(self, address: int) -> Optional[int]:
        data = self.read_cached(address, 8)
        return None if data is None else struct.unpack("<q", data)[0]

    def u32(self, address: int) -> Optional[int]:
        data = self.read_cached(address, 4)
        return None if data is None else struct.unpack("<I", data)[0]

    def i32(self, address: int) -> Optional[int]:
        data = self.read_cached(address, 4)
        return None if data is None else struct.unpack("<i", data)[0]

    def f64(self, address: int) -> Optional[float]:
        data = self.read_cached(address, 8)
        return None if data is None else struct.unpack("<d", data)[0]

    def cstring(self, address: int, limit: int = 0x100) -> Optional[str]:
        data = self.try_read(address, limit)
        if data is None:
            # Near the end of a region a shorter read may still succeed.
            for smaller in (0x40, 0x20, 0x10):
                if smaller >= limit:
                    continue
                data = self.try_read(address, smaller)
                if data is not None:
                    break
        if data is None:
            return None
        end = data.find(b"\0")
        if end < 0:
            return None
        try:
            return data[:end].decode("ascii")
        except UnicodeDecodeError:
            return None

    # -- regions -----------------------------------------------------------

    def regions(self, readable_only: bool = True) -> Iterator[Region]:
        address = 0
        info = MEMORY_BASIC_INFORMATION64()
        while address < (1 << 47):
            got = _k32.VirtualQueryEx(
                self._handle, ctypes.c_void_p(address), ctypes.byref(info), ctypes.sizeof(info)
            )
            if not got:
                break
            base, size, protect, state = (
                info.BaseAddress,
                info.RegionSize,
                info.Protect,
                info.State,
            )
            if size == 0:
                break
            usable = (
                state == MEM_COMMIT
                and not (protect & PAGE_GUARD)
                and (protect & 0xFF) in READABLE_PROTECT
            )
            if usable or not readable_only:
                yield Region(base, size, protect)
            address = base + size


# --------------------------------------------------------------------------
# PE export table, read out of the target's own memory
# --------------------------------------------------------------------------


def module_exports(reader: ProcessReader, module_base: int) -> dict[str, int]:
    """Parse a loaded module's export directory and return {name: address}.

    Read from the target rather than from the file on disk, so the addresses are
    the ones this process is actually using and no relocation arithmetic is
    needed.
    """
    head = reader.try_read(module_base, 0x400)
    if head is None or head[:2] != b"MZ":
        raise MemoryReadError(f"no PE header at 0x{module_base:X}")
    e_lfanew = struct.unpack_from("<I", head, 0x3C)[0]
    nt = reader.try_read(module_base + e_lfanew, 0x108)
    if nt is None or nt[:4] != b"PE\0\0":
        raise MemoryReadError(f"no NT header at 0x{module_base + e_lfanew:X}")
    magic = struct.unpack_from("<H", nt, 0x18)[0]
    if magic != 0x20B:
        raise MemoryReadError(
            f"module at 0x{module_base:X} is not PE32+ (optional header magic 0x{magic:X})"
        )
    # Data directory 0 is the export table; it starts at 0x88 in the PE32+
    # optional header, which itself starts at 0x18 past the signature+file header.
    export_rva, export_size = struct.unpack_from("<II", nt, 0x18 + 0x70)
    if not export_rva:
        return {}
    directory = reader.try_read(module_base + export_rva, 0x28)
    if directory is None:
        raise MemoryReadError("export directory unreadable")
    (
        _flags,
        _stamp,
        _major,
        _minor,
        _name_rva,
        ordinal_base,
        address_count,
        name_count,
        address_rva,
        name_pointer_rva,
        ordinal_rva,
    ) = struct.unpack("<IIHHIIIIIII", directory)

    functions = reader.try_read(module_base + address_rva, 4 * address_count)
    name_pointers = reader.try_read(module_base + name_pointer_rva, 4 * name_count)
    ordinals = reader.try_read(module_base + ordinal_rva, 2 * name_count)
    if functions is None or name_pointers is None or ordinals is None:
        raise MemoryReadError("export tables unreadable")

    out: dict[str, int] = {}
    for i in range(name_count):
        name_rva = struct.unpack_from("<I", name_pointers, 4 * i)[0]
        name = reader.cstring(module_base + name_rva, 0x100)
        if not name:
            continue
        ordinal = struct.unpack_from("<H", ordinals, 2 * i)[0]
        if ordinal >= address_count:
            continue
        func_rva = struct.unpack_from("<I", functions, 4 * ordinal)[0]
        # A forwarder RVA points back inside the export directory; those are not
        # real addresses and there is nothing here that wants one.
        if export_rva <= func_rva < export_rva + export_size:
            continue
        out[name] = module_base + func_rva
    return out


# --------------------------------------------------------------------------
# Python object decoding
# --------------------------------------------------------------------------


@dataclass
class Types:
    """Addresses of the CPython type objects, taken from python27.dll's exports."""

    by_address: dict[int, str] = field(default_factory=dict)
    by_name: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def from_exports(exports: dict[str, int]) -> "Types":
        wanted = {
            "PyType_Type": "type",
            "PyString_Type": "str",
            "PyUnicode_Type": "unicode",
            "PyInt_Type": "int",
            "PyLong_Type": "long",
            "PyFloat_Type": "float",
            "PyBool_Type": "bool",
            "PyList_Type": "list",
            "PyTuple_Type": "tuple",
            "PyDict_Type": "dict",
            "PyWeakref_RefType": "weakref",
            "_Py_NoneStruct": "NoneType",
        }
        t = Types()
        for symbol, friendly in wanted.items():
            address = exports.get(symbol)
            if address is None:
                continue
            t.by_name[friendly] = address
            t.by_address[address] = friendly
        return t


class PyReader:
    """Decodes CPython 2.7 objects out of a live process.

    Every method answers ``None`` for a read it could not make or a shape it did
    not recognise, and never a defaulted value.  CLAUDE.md's rule -- absent is
    not false, and a fabricated value reads exactly like a real one -- is the
    whole reason this port is risky, so it is enforced at the bottom.
    """

    def __init__(self, reader: ProcessReader, layout: Layout, types: Types):
        self.r = reader
        self.L = layout
        self.types = types
        # Per-request memos. Profiling one real tree found 1,163,675 reads for
        # 3,617 nodes -- a 15.5x repeat factor, with one address read 60,824
        # times -- because `primitive` tries decoders in turn and each one
        # re-reads `ob_type` to check whether it applies. Memoizing the two
        # hottest answers collapses that without changing any of them.
        #
        # Scoped to a request for the same reason the page cache is: holding
        # them across reads would hand the bot a tree blended from moments
        # seconds apart. Within one walk they are a consistency *gain*.
        self._type_memo: dict[int, Optional[int]] = {}
        self._str_memo: dict[int, Optional[bytes]] = {}

    def begin_request(self) -> None:
        self._type_memo.clear()
        self._str_memo.clear()

    end_request = begin_request

    # -- header ------------------------------------------------------------

    def type_of(self, address: int) -> Optional[int]:
        memo = self._type_memo
        if address in memo:
            return memo[address]
        value = self.r.u64(address + self.L.ob_type)
        memo[address] = value
        return value

    def type_name(self, address: int) -> Optional[str]:
        """The ``tp_name`` of the object's type, i.e. its class name."""
        type_address = self.type_of(address)
        if not type_address:
            return None
        return self.type_name_of_type(type_address)

    def type_name_of_type(self, type_address: int) -> Optional[str]:
        name_pointer = self.r.u64(type_address + self.L.tp_name)
        if not name_pointer:
            return None
        return self.r.cstring(name_pointer, 0x80)

    def is_type_object(self, address: int) -> bool:
        """``type(type) is type`` -- the one process-independent invariant."""
        metatype = self.types.by_name.get("type")
        if metatype is None:
            return False
        return self.type_of(address) == metatype

    # -- scalars -----------------------------------------------------------

    def read_str(self, address: int) -> Optional[bytes]:
        """Python 2 ``str``: PyObject_VAR_HEAD, ob_shash, ob_sstate, then chars.

        Memoized per request: a UI tree's dict keys are interned, so the same few
        dozen strings (``_name``, ``_displayX``, ``children`` …) are decoded once
        per node otherwise -- 229,466 calls on one real tree.
        """
        memo = self._str_memo
        if address in memo:
            return memo[address]
        value = self._read_str_uncached(address)
        memo[address] = value
        return value

    def _read_str_uncached(self, address: int) -> Optional[bytes]:
        if self.type_of(address) != self.types.by_name.get("str"):
            return None
        size = self.r.i64(address + self.L.ob_size)
        if size is None or size < 0 or size > (1 << 20):
            return None
        if size == 0:
            return b""
        return self.r.read_cached(address + self.L.str_chars, size)

    def read_int(self, address: int) -> Optional[int]:
        """Python 2 ``int``/``bool``: a bare ``long``, whose width is the platform's."""
        type_address = self.type_of(address)
        if type_address not in (
            self.types.by_name.get("int"),
            self.types.by_name.get("bool"),
        ):
            return None
        if self.L.int_value_size == 4:
            return self.r.i32(address + self.L.int_value)
        return self.r.i64(address + self.L.int_value)

    def read_long(self, address: int) -> Optional[int]:
        """Python 2 ``long``: sign and digit count in ob_size, 30-bit digits after.

        Accumulated in Python's own arbitrary precision.  CLAUDE.md records a
        ``double`` accumulator losing real in-game timestamps above 2**53.
        """
        if self.type_of(address) != self.types.by_name.get("long"):
            return None
        ob_size = self.r.i64(address + self.L.ob_size)
        if ob_size is None or abs(ob_size) > 512:
            return None
        count = abs(ob_size)
        if count == 0:
            return 0
        digits = self.r.read_cached(address + self.L.long_digits, 4 * count)
        if digits is None:
            return None
        value = 0
        for i in reversed(range(count)):
            digit = struct.unpack_from("<I", digits, 4 * i)[0]
            if digit >= (1 << 30):
                return None
            value = (value << 30) | digit
        return -value if ob_size < 0 else value

    def read_float(self, address: int) -> Optional[float]:
        if self.type_of(address) != self.types.by_name.get("float"):
            return None
        return self.r.f64(address + self.L.float_value)

    def read_unicode(self, address: int) -> Optional[str]:
        if self.type_of(address) != self.types.by_name.get("unicode"):
            return None
        length = self.r.i64(address + self.L.unicode_length)
        buffer = self.r.u64(address + self.L.unicode_buffer)
        if length is None or buffer is None or length < 0 or length > (1 << 20):
            return None
        if length == 0:
            return ""
        width = self.L.unicode_char_size
        raw = self.r.read_cached(buffer, width * length)
        if raw is None:
            return None
        try:
            # Surrogates are legal in a Python 2 UCS-2 buffer and Python 3 will
            # not decode a lone one, so they are preserved rather than refused --
            # dropping the whole string because one character is a surrogate half
            # would be the same silent loss this width bug already caused.
            return raw.decode("utf-16-le" if width == 2 else "utf-32-le",
                              errors="surrogatepass")
        except (UnicodeDecodeError, ValueError):
            return None

    def read_list(self, address: int) -> Optional[list[int]]:
        """A stock ``PyListObject``: ob_size, then a flat array of pointers."""
        if self.type_of(address) != self.types.by_name.get("list"):
            return None
        size = self.r.i64(address + self.L.ob_size)
        items = self.r.u64(address + self.L.list_items)
        if size is None or items is None or size < 0 or size > (1 << 20):
            return None
        if size == 0:
            return []
        raw = self.r.read_cached(items, 8 * size)
        if raw is None:
            return None
        return list(struct.unpack_from(f"<{size}Q", raw, 0))

    def read_weakref_target(self, address: int) -> Optional[int]:
        if self.type_of(address) != self.types.by_name.get("weakref"):
            return None
        return self.r.u64(address + self.L.weakref_object)

    def scalar(self, address: int):
        """Decode whatever primitive this is, or ``None`` if it is not one.

        Returns ``(kind, value)`` so that a genuine ``None`` value and an
        undecodable object are distinguishable at the call site -- the
        ``Nothing`` versus ``Just Nothing`` distinction the Elm side depends on.
        """
        if not address:
            return None
        type_address = self.type_of(address)
        if type_address is None:
            return None
        # `_Py_NoneStruct` is the None *singleton* rather than its type, so the
        # test is on the object's own address.
        if address == self.types.by_name.get("NoneType"):
            return ("none", None)
        for kind, fn in (
            ("str", self.read_str),
            ("unicode", self.read_unicode),
            ("int", self.read_int),
            ("long", self.read_long),
            ("float", self.read_float),
        ):
            value = fn(address)
            if value is not None:
                if kind == "str":
                    try:
                        return ("str", value.decode("utf-8"))
                    except UnicodeDecodeError:
                        return ("str", value.decode("latin-1"))
                return (kind, value)
        return None


def find_client_pid() -> Optional[int]:
    """The EVE client's pid, without ever touching an argument vector.

    CLAUDE.md: the launcher starts the game with ``/ssoToken=`` and
    ``/refreshToken=`` on the command line, so anything that prints a command
    line dumps live credentials into a log or a transcript.  This matches on the
    executable path only.
    """
    import subprocess

    out = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process exefile -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Path -like '*bin64*exefile.exe' } | "
            "Sort-Object WorkingSet64 -Descending | "
            "Select-Object -First 1 -ExpandProperty Id",
        ],
        capture_output=True,
        text=True,
    )
    text = out.stdout.strip()
    return int(text) if text.isdigit() else None


def module_bases(pid: int) -> dict[str, int]:
    """{module name: base address} for a process, via the toolhelp snapshot."""
    import subprocess

    out = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Process -Id {pid}).Modules | "
            "ForEach-Object { $_.ModuleName + '=' + $_.BaseAddress.ToInt64() }",
        ],
        capture_output=True,
        text=True,
    )
    bases: dict[str, int] = {}
    for line in out.stdout.splitlines():
        if "=" in line:
            name, _, value = line.strip().rpartition("=")
            if value.lstrip("-").isdigit():
                bases[name] = int(value) & 0xFFFFFFFFFFFFFFFF
    return bases


if __name__ == "__main__":
    if struct.calcsize("P") != 8:
        sys.exit("this must run under 64-bit Python to read a 64-bit client")
    pid = find_client_pid()
    print(f"client pid: {pid}")
