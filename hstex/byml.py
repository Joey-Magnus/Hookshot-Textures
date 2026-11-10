"""BYML (versions 2 to 7, little endian): the game's parameter files (.bgyml, .byml, .byml.zs).

parse(data) -> Python values; write(value) -> bytes. Scalar types survive a round trip through these classes:
  int -> Int (0xD1), float -> Float (0xD2), U32 (0xD3), I64 (0xD4), U64 (0xD5), F64 (0xD6), bool (0xD0), str (0xA0),
  Binary (0xA1), None (0xFF), list (0xC0), dict (0xC1).
Plain int and float are written as Int and Float, so a new value set from Python keeps the type a file uses for it only
if the caller gives it that type (params.py does: an override takes the type of the value it replaces).
"""
from __future__ import annotations

import struct


class U32(int):
    pass


class I64(int):
    pass


class U64(int):
    pass


class F64(float):
    pass


class Binary(bytes):
    pass


class AlignedBinary(bytes):
    """0xA2: binary data with an alignment (.align)."""
    align = 4

    def __new__(cls, data, align=4):
        o = super().__new__(cls, data)
        o.align = align
        return o


class HashMap32(dict):
    """0x20: a map keyed by 32-bit hashes (ints), entries sorted by hash."""


class HashMap64(dict):
    """0x21: a map keyed by 64-bit hashes."""


class BymlError(ValueError):
    pass


def _as_float(v: int) -> float:
    return struct.unpack("<f", struct.pack("<I", v))[0]


def _bits_float(f: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f))[0]


def parse(d: bytes):
    if d[:2] != b"YB":
        raise BymlError("not little-endian BYML (magic %r)" % d[:2])
    version = struct.unpack_from("<H", d, 2)[0]
    ko, so, ro = struct.unpack_from("<III", d, 4)

    def strtab(off):
        if not off:
            return []
        if d[off] != 0xC2:
            raise BymlError("string table at %#x has type %#x" % (off, d[off]))
        n = struct.unpack_from("<I", d, off)[0] >> 8
        offs = struct.unpack_from("<%dI" % (n + 1), d, off + 4)
        return [d[off + o:d.index(b"\0", off + o)].decode("utf-8") for o in offs[:n]]

    keys, strs = strtab(ko), strtab(so)

    def val(t, v):
        if t == 0xA0:
            return strs[v]
        if t == 0xA2:
            n, a = struct.unpack_from("<II", d, v)
            return AlignedBinary(d[v + 8:v + 8 + n], a)
        if t == 0xA1:
            n = struct.unpack_from("<I", d, v)[0]
            return Binary(d[v + 4:v + 4 + n])
        if t == 0xD0:
            return bool(v)
        if t == 0xD1:
            return struct.unpack("<i", struct.pack("<I", v))[0]
        if t == 0xD2:
            return _as_float(v)
        if t == 0xD3:
            return U32(v)
        if t == 0xD4:
            return I64(struct.unpack_from("<q", d, v)[0])
        if t == 0xD5:
            return U64(struct.unpack_from("<Q", d, v)[0])
        if t == 0xD6:
            return F64(struct.unpack_from("<d", d, v)[0])
        if t == 0xFF:
            return None
        if t in (0xC0, 0xC1, 0x20, 0x21):
            return node(v)
        raise BymlError("node type %#x not handled" % t)

    def node(off):
        t = d[off]
        n = struct.unpack_from("<I", d, off)[0] >> 8
        if t == 0xC0:
            types = d[off + 4:off + 4 + n]
            base = off + 4 + ((n + 3) & ~3)
            return [val(types[i], struct.unpack_from("<I", d, base + 4 * i)[0]) for i in range(n)]
        if t == 0xC1:
            out = {}
            for i in range(n):
                e = off + 4 + 8 * i
                k = struct.unpack_from("<I", d, e)[0] & 0xFFFFFF
                out[keys[k]] = val(d[e + 3], struct.unpack_from("<I", d, e + 4)[0])
            return out
        if t in (0x20, 0x21):
            w = 8 if t == 0x20 else 12
            types = d[off + 4 + w * n:off + 4 + w * n + n]
            out = HashMap32() if t == 0x20 else HashMap64()
            for i in range(n):
                e = off + 4 + w * i
                h = struct.unpack_from("<I" if t == 0x20 else "<Q", d, e)[0]
                out[h] = val(types[i], struct.unpack_from("<I", d, e + w - 4)[0])
            return out
        raise BymlError("container type %#x at %#x not handled" % (t, off))

    root = node(ro) if ro else None
    return root, version


def _type_of(v) -> int:
    if v is None:
        return 0xFF
    if isinstance(v, bool):
        return 0xD0
    if isinstance(v, U32):
        return 0xD3
    if isinstance(v, I64):
        return 0xD4
    if isinstance(v, U64):
        return 0xD5
    if isinstance(v, int):
        return 0xD1
    if isinstance(v, F64):
        return 0xD6
    if isinstance(v, float):
        return 0xD2
    if isinstance(v, AlignedBinary):
        return 0xA2
    if isinstance(v, Binary):
        return 0xA1
    if isinstance(v, str):
        return 0xA0
    if isinstance(v, list):
        return 0xC0
    if isinstance(v, HashMap32):
        return 0x20
    if isinstance(v, HashMap64):
        return 0x21
    if isinstance(v, dict):
        return 0xC1
    raise BymlError("no BYML type for %r" % type(v))


def write(root, version: int = 7) -> bytes:
    keys, strs = set(), set()

    def collect(v):
        if isinstance(v, (HashMap32, HashMap64)):
            for x in v.values():
                collect(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                keys.add(k)
                collect(x)
        elif isinstance(v, list):
            for x in v:
                collect(x)
        elif isinstance(v, str):
            strs.add(v)

    collect(root)
    # (sorted by their UTF-8 bytes: the game looks keys up by binary search)
    key_list = sorted(keys, key=lambda s: s.encode())
    str_list = sorted(strs, key=lambda s: s.encode())
    key_ix = {k: i for i, k in enumerate(key_list)}
    str_ix = {s: i for i, s in enumerate(str_list)}

    out = bytearray(16)

    def align(n):
        while len(out) % n:
            out.append(0)

    def strtab(lst):
        if not lst:
            return 0
        align(4)
        off = len(out)
        enc = [s.encode() + b"\0" for s in lst]
        hdr = 4 + 4 * (len(lst) + 1)
        offs, at = [], hdr
        for e in enc:
            offs.append(at)
            at += len(e)
        offs.append(at)
        out.extend(struct.pack("<I", 0xC2 | (len(lst) << 8)) + struct.pack("<%dI" % len(offs), *offs))
        for e in enc:
            out.extend(e)
        return off

    ko = strtab(key_list)
    so = strtab(str_list)

    # Containers: the root first, then each container's children after it (breadth first by level), as the game's
    # files are laid out. 64-bit values and binaries follow the container that holds them.
    def scalar(v, t, pending):
        if t == 0xA0:
            return str_ix[v]
        if t == 0xD0:
            return 1 if v else 0
        if t == 0xD1:
            return v & 0xFFFFFFFF
        if t == 0xD2:
            return _bits_float(v)
        if t == 0xD3:
            return int(v)
        if t == 0xFF:
            return 0
        pending.append(v)   # (patched below: an offset)
        return None

    CONTAINERS = (0xC0, 0xC1, 0x20, 0x21)
    done = {}   # (identical containers written once, as the game's files have them)

    def canon(v):
        t = _type_of(v)
        if t == 0xC0:
            return (t, tuple(canon(x) for x in v))
        if t in (0xC1, 0x20, 0x21):
            return (t, tuple(sorted((k, canon(x)) for k, x in v.items())))
        if t == 0xD2:
            return (t, _bits_float(v))
        if t == 0xA2:
            return (t, v.align, bytes(v))
        return (t, v)

    def emit(v) -> int:
        key = canon(v)
        if key in done:
            return done[key]
        align(4)
        off = len(out)
        done[key] = off
        t0 = _type_of(v)
        if t0 == 0xC0:
            items = [(None, x) for x in v]
            out.extend(struct.pack("<I", 0xC0 | (len(items) << 8)))
            out.extend(bytes(_type_of(x) for _, x in items))
            align(4)
        elif t0 == 0xC1:
            items = sorted(v.items(), key=lambda kv: key_ix[kv[0]])
            out.extend(struct.pack("<I", 0xC1 | (len(items) << 8)))
        else:
            items = sorted(v.items())
            out.extend(struct.pack("<I", t0 | (len(items) << 8)))
        slots = []
        for k, x in items:
            t = _type_of(x)
            s = scalar(x, t, []) if t not in CONTAINERS else None
            at = len(out)
            if t0 == 0xC0:
                out.extend(struct.pack("<I", s or 0))
                slot = at
            elif t0 == 0xC1:
                out.extend(struct.pack("<I", key_ix[k] | (t << 24)) + struct.pack("<I", s or 0))
                slot = at + 4
            else:
                out.extend(struct.pack("<I" if t0 == 0x20 else "<Q", k) + struct.pack("<I", s or 0))
                slot = len(out) - 4
            if s is None:
                slots.append((slot, t, x))
        if t0 in (0x20, 0x21):
            out.extend(bytes(_type_of(x) for _, x in items))
            align(4)
        for slot, t, x in slots:
            if t in CONTAINERS:
                continue
            if t == 0xA2:   # (the data at its alignment, the 8-byte header just before it)
                while (len(out) + 8) % max(4, x.align):
                    out.append(0)
            else:
                align(8 if t in (0xD4, 0xD5, 0xD6) else 4)
            at = len(out)
            if t == 0xD4:
                out.extend(struct.pack("<q", x))
            elif t == 0xD5:
                out.extend(struct.pack("<Q", x))
            elif t == 0xD6:
                out.extend(struct.pack("<d", x))
            elif t == 0xA2:
                out.extend(struct.pack("<II", len(x), x.align) + x)
            elif t == 0xA1:
                out.extend(struct.pack("<I", len(x)) + x)
            struct.pack_into("<I", out, slot, at)
        for slot, t, x in slots:
            if t in CONTAINERS:
                struct.pack_into("<I", out, slot, emit(x))
        return off

    ro = emit(root) if root is not None else 0
    align(4)
    struct.pack_into("<2sHIII", out, 0, b"YB", version, ko, so, ro)
    return bytes(out)


def get_path(root, path: str):
    """'A.B[2].C' -> the value there."""
    v = root
    for part, ix in _split(path):
        v = v[part] if part is not None else v[ix]
    return v


def _split(path: str):
    out = []
    for seg in path.split("."):
        while seg:
            if seg.startswith("["):
                j = seg.index("]")
                out.append((None, int(seg[1:j])))
                seg = seg[j + 1:]
            else:
                j = seg.find("[")
                name = seg if j < 0 else seg[:j]
                out.append((name, None))
                seg = "" if j < 0 else seg[j:]
    return out


def set_path(root, path: str, value, create: bool = False):
    """Sets the value at path. The new value takes the old one's BYML type (an int for a float key stays a float);
    with create, a missing last key is added (typed from the Python value). Returns the old value (None if added)."""
    parts = _split(path)
    v = root
    for part, ix in parts[:-1]:
        v = v[part] if part is not None else v[ix]
    part, ix = parts[-1]
    if part is not None and part not in v:
        if not create:
            raise KeyError(path)
        v[part] = value
        return None
    old = v[part] if part is not None else v[ix]
    new = coerce(value, old)
    if part is not None:
        v[part] = new
    else:
        v[ix] = new
    return old


def patch_int(d: bytes, path: str, value: int) -> bytes:
    """The file with the 32-bit int (0xD1) or uint (0xD3) at a dict-only path ('A.B.C') changed in place; every
    other byte stays as it was."""
    ko = struct.unpack_from("<I", d, 4)[0]
    off = struct.unpack_from("<I", d, 12)[0]
    n = struct.unpack_from("<I", d, ko)[0] >> 8
    offs = struct.unpack_from("<%dI" % (n + 1), d, ko + 4)
    key_ix = {d[ko + o:d.index(b"\0", ko + o)].decode("utf-8"): i for i, o in enumerate(offs[:n])}
    names = path.split(".")
    for depth, name in enumerate(names):
        if d[off] != 0xC1:
            raise BymlError("%s: not a dict at %#x" % (path, off))
        count = struct.unpack_from("<I", d, off)[0] >> 8
        want = key_ix.get(name)
        for i in range(count):
            e = off + 4 + 8 * i
            if want is not None and struct.unpack_from("<I", d, e)[0] & 0xFFFFFF == want:
                break
        else:
            raise KeyError(path)
        t = d[e + 3]
        if depth < len(names) - 1:
            off = struct.unpack_from("<I", d, e + 4)[0]
            continue
        if t not in (0xD1, 0xD3):
            raise BymlError("%s holds type %#x, not an int" % (path, t))
        out = bytearray(d)
        struct.pack_into("<i" if t == 0xD1 else "<I", out, e + 4, value)
        return bytes(out)


def coerce(value, like):
    """value converted to the BYML type of like."""
    if like is None or isinstance(like, (dict, list)):
        return value
    t = _type_of(like)
    if t == 0xD0:
        return bool(value)
    if t == 0xD2:
        return float(value)
    if t == 0xD6:
        return F64(value)
    if t == 0xD1:
        if float(value) != int(value):
            raise BymlError("%r is not an integer (the key holds one)" % value)
        return int(value)
    if t == 0xD3:
        return U32(int(value))
    if t == 0xD4:
        return I64(int(value))
    if t == 0xD5:
        return U64(int(value))
    if t == 0xA0:
        return str(value)
    return value
