"""Which textures of a pack came from BC1 originals that use punch-through alpha (the cut-outs the old decoder lost).
python -m tests.punch_scan <game romfs> <pack romfs/Tex> <out.json>"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from hstex import bntx, zs

ROMFS = sys.argv[1]


def check(name: str):
    t = bntx.parse(zs.decompress(Path(ROMFS, "Tex", name).read_bytes(), ROMFS))
    if t.fmt_name != "BC1":
        return None
    a = bntx.decode_mip0(t)[..., 3]
    cut = float((a == 0).mean())
    return (name, round(cut, 4)) if cut > 0 else None


if __name__ == "__main__":
    names = sorted(p.name for p in Path(sys.argv[2]).glob("*.bntx.zs"))
    with ProcessPoolExecutor(14) as ex:
        hits = [h for h in ex.map(check, names, chunksize=16) if h]
    json.dump(hits, open(sys.argv[3], "w"))
    print(len(hits), "pack textures came from punch-through BC1 originals")
    for n, c in sorted(hits, key=lambda h: -h[1])[:12]:
        print(f"  {c:.3f}  {n}")
