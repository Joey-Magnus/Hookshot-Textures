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

    def merge(self, other: "Rstb") -> int:
        """Every entry of another table grown into this one (the larger size kept). Returns how many grew."""
        grown = 0
        for c, s in other.crc.items():
            if self.crc.get(c, 0) < s:
                self.crc[c] = s
                grown += 1
        for name, s in other.names.items():
            if self.names.get(name, 0) < s:
                self.names[name] = s
                grown += 1
        return grown

    def dump(self) -> bytes:
        out = bytearray(b"RESTBL")
        out += struct.pack("<IIII", self.version, self.name_len, len(self.crc), len(self.names))
        for c in sorted(self.crc):
            out += struct.pack("<II", c, self.crc[c])
        for name in sorted(self.names):
            out += name.encode().ljust(self.name_len, b"\0") + struct.pack("<I", self.names[name])
        return bytes(out)


TABLE_MOD = "99-ResourceSizeTable"


def mod_romfs_dirs(mods: Path) -> list[tuple[str, Path]]:
    """(mod name, its romfs folder) for every enabled mod, in the loader's order (by name; '-' or '_' first turns a mod
    off). A mod is mods/<name>/romfs, or deeper (mods/contents/<title id>/<name>/romfs) as emulators lay them out. The
    table's own mod is left out"""
    found = []
    for romfs in sorted(mods.rglob("romfs")):
        if not romfs.is_dir():
            continue
        parts = romfs.relative_to(mods).parts
        if len(parts) < 2 or any(p.startswith(("-", "_")) for p in parts[:-1]) or parts[-2] == TABLE_MOD:
            continue
        if any(p == "romfs" for p in parts[:-1]):   # (a folder named romfs inside a mod's own romfs)
            continue
        found.append(("/".join(parts[:-1]), romfs))
    return sorted(found, key=lambda m: m[0])


def file_need(f: Path) -> int:
    """The entry a mod file needs: its decompressed size (.zs: from the frame header) plus the loader's overhead"""
    if f.name.endswith(".zs"):
        with open(f, "rb") as fh:
            return zs.content_size(fh.read(32)) + OVERHEAD
    return f.stat().st_size + OVERHEAD


def regenerate(game: str | Path, romfs: str | Path | None = None) -> dict:
    """mods/99-ResourceSizeTable rebuilt from the game's own table and every enabled mod: each mod file's entry grown
    to fit it, and the entries of any table a mod ships merged in (only the last mod's table is used, which is this one).
    Entries only grow. Run again after a mod is installed, removed or turned on or off"""
    game = Path(game)
    romfs = str(romfs or game / "romfs")
    table = Rstb.load(romfs)
    mods = game / "mods"
    report = {"mods": [], "grown": 0, "tables": []}
    for name, mod_romfs in mod_romfs_dirs(mods) if mods.is_dir() else []:
        files = 0
        for f in mod_romfs.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(mod_romfs).as_posix()
            if rel == NAME:
                report["grown"] += table.merge(Rstb(zs.decompress(f.read_bytes(), romfs)))
                report["tables"].append(name)
                continue
            path = rel[:-3] if rel.endswith(".zs") else rel
            need = file_need(f)
            files += 1
            if (table.get(path) or 0) < need:
                table.set(path, need)
                report["grown"] += 1
        report["mods"].append((name, files))
    out = mods / TABLE_MOD / "romfs" / NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_bytes(zs.compress(table.dump()))
    tmp.replace(out)
    report["out"] = str(out)
    return report
