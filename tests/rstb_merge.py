"""mods/99-ResourceSizeTable from every enabled mod: python -m tests.rstb_merge (from the repository root).

No game data: a made-up table and made-up mod files in a temporary folder.
"""
import sys
import tempfile
import zlib
from pathlib import Path

from hstex import rstb, zs

failures = []


def check(what, got, want):
    if got != want:
        failures.append(f"{what}: {got!r}, {want!r} expected")


def table(entries: dict[str, int]) -> rstb.Rstb:
    t = rstb.Rstb(b"RESTBL" + (1).to_bytes(4, "little") + (160).to_bytes(4, "little") + bytes(8))
    for path, size in entries.items():
        t.set(path, size)
    return t


def write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


with tempfile.TemporaryDirectory() as tmp:
    game = Path(tmp)
    write(game / "romfs" / rstb.NAME, zs.compress(table({"Tex/A.bntx": 1000, "Tex/B.bntx": 5000,
                                                         "Param/P.bgyml": 300}).dump()))
    mods = game / "mods"
    write(mods / "01-Tex/romfs/Tex/A.bntx.zs", zs.compress(bytes(4000)))     # grows: 4000 + 280
    write(mods / "01-Tex/romfs/Tex/B.bntx.zs", zs.compress(bytes(100)))      # smaller: entry kept
    # (a mod that ships its own table, as 01-HD-Textures does: merged in)
    write(mods / "01-Tex/romfs" / rstb.NAME, zs.compress(table({"Tex/C.bntx": 7777}).dump()))
    write(mods / "02-Params/romfs/Param/P.bgyml", bytes(500))                 # a loose file: 500 + 280
    write(mods / "contents/0100/03-Deep/romfs/Tex/D.bntx.zs", zs.compress(bytes(10)))   # an emulator layout
    write(mods / "_04-Off/romfs/Tex/A.bntx.zs", zs.compress(bytes(90000)))   # turned off: not counted
    write(mods / "-05-Off/romfs/Tex/E.bntx.zs", zs.compress(bytes(90000)))   # turned off too

    names = [n for n, _ in rstb.mod_romfs_dirs(mods)]
    check("enabled mods", names, ["01-Tex", "02-Params", "contents/0100/03-Deep"])

    r = rstb.regenerate(game)
    out = rstb.Rstb(zs.decompress(Path(r["out"]).read_bytes(), str(game / "romfs")))
    check("written as its own mod", Path(r["out"]).relative_to(mods).parts[0], rstb.TABLE_MOD)
    check("A grown", out.get("Tex/A.bntx"), 4000 + rstb.OVERHEAD)
    check("B kept", out.get("Tex/B.bntx"), 5000)
    check("C from a mod's table", out.get("Tex/C.bntx"), 7777)
    check("P loose file", out.get("Param/P.bgyml"), 500 + rstb.OVERHEAD)
    check("D deep layout", out.get("Tex/D.bntx"), 10 + rstb.OVERHEAD)
    check("E off", out.get("Tex/E.bntx"), None)
    check("by CRC32", out.crc.get(zlib.crc32(b"Tex/A.bntx")), 4000 + rstb.OVERHEAD)
    check("tables merged", r["tables"], ["01-Tex"])

    # (run again: its own output is not read back as a mod, and nothing changes)
    before = Path(r["out"]).read_bytes()
    r2 = rstb.regenerate(game)
    check("second run same table", Path(r2["out"]).read_bytes(), before)
    check("second run mods", [n for n, _ in r2["mods"]], names)

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("rstb merge: ok")
