"""The resource size table (System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs, "RESTBL"):
the memory the loader sets aside for each file, by CRC32 of its path (paths that collide are listed by name instead).
A file that outgrows its entry does not load, so a pack that makes textures bigger needs its own table."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from . import zs

NAME = "System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
OVERHEAD = 280


class Rstb:
    def __init__(self, raw: bytes):
        if raw[:6] != b"RESTBL":
            raise ValueError("not a RESTBL")
        self.version, self.name_len, n_crc, n_name = struct.unpack_from("<IIII", raw, 6)
        at = 22
        self.crc: dict[int, int] = {}
        for _ in range(n_crc):
            c, s = struct.unpack_from("<II", raw, at)
            self.crc[c] = s
            at += 8
        self.names: dict[str, int] = {}
        for _ in range(n_name):
            name = raw[at:at + self.name_len].split(b"\0", 1)[0].decode()
            self.names[name] = struct.unpack_from("<I", raw, at + self.name_len)[0]
            at += self.name_len + 4

    @classmethod
    def load(cls, romfs: str) -> "Rstb":
        return cls(zs.decompress(Path(romfs, NAME).read_bytes(), romfs))

    def get(self, path: str) -> int | None:
        if path in self.names:
            return self.names[path]
        return self.crc.get(zlib.crc32(path.encode()))

    def set(self, path: str, size: int) -> None:
        if path in self.names:
            self.names[path] = size
        else:
            self.crc[zlib.crc32(path.encode())] = size

    def fit_mod(self, mod: str | Path) -> int:
        """Entries for every file of a mod's romfs grown to its decompressed size plus the loader's overhead (the
        shipped entries are the size + 280); the table written into the mod. Returns how many entries grew."""
        romfs = Path(mod, "romfs")
        grown = 0
        for f in romfs.rglob("*.zs"):
            rel = f.relative_to(romfs).as_posix()
            if rel == NAME:
                continue
            path = rel[:-3]
            with open(f, "rb") as fh:
                size = zs.content_size(fh.read(32))
            need = size + OVERHEAD
            if (self.get(path) or 0) < need:
                self.set(path, need)
                grown += 1
        out = romfs / NAME
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zs.compress(self.dump()))
        return grown

    def dump(self) -> bytes:
        out = bytearray(b"RESTBL")
        out += struct.pack("<IIII", self.version, self.name_len, len(self.crc), len(self.names))
        for c in sorted(self.crc):
            out += struct.pack("<II", c, self.crc[c])
        for name in sorted(self.names):
            out += name.encode().ljust(self.name_len, b"\0") + struct.pack("<I", self.names[name])
        return bytes(out)
