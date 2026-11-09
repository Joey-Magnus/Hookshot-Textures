"""The tiling math against the shipped files: mip offsets, the base block height and where the relocation table
sits, for every texture of one kind (default Alb)."""
import collections
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hstex import bntx, zs  # noqa: E402

ROMFS = "/home/voidm/Games/OcarinaOfTime/romfs"


def one(path: str):
    try:
        t = bntx.parse(zs.decompress(Path(path).read_bytes(), ROMFS))
    except Exception as e:  # noqa: BLE001
        return path, "parse: " + str(e)[:80]
    if t.fmt_type not in bntx.FORMATS:
        return path, f"format {t.fmt_type:#x}"
    if t.depth != 1 or t.layers != 1:
        return path, f"depth {t.depth} layers {t.layers}"
    hb = bntx.div_up(t.height, bntx.FORMATS[t.fmt_type][2])
    if t.bh0 not in (1, bntx.block_height_mip0(hb)):
        return path, f"bh0 {t.bh0}: neither 1 nor computed {bntx.block_height_mip0(hb)}"
    if not bntx.check_layout(t):
        return path, "mip offsets"
    end = t.mip_ptrs[0] + sum(s for _, s, *_ in bntx.mip_layout(t.width, t.height, t.fmt_type, t.mips, t.bh0))
    return path, f"ok rlt-gap {t.rlt - end} rlt%4k {t.rlt % 0x1000 == 0} data%{t.mip_ptrs[0] % 0x1000}"


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "Alb"
    files = sorted(str(p) for p in Path(ROMFS, "Tex").glob(f"*_{kind}.bntx.zs"))
    res = collections.Counter()
    bad = []
    with ProcessPoolExecutor() as ex:
        for path, r in ex.map(one, files, chunksize=32):
            key = r if not r.startswith("ok") else "ok " + r.split(" rlt-gap ")[1].split(" ", 1)[1]
            res[key] += 1
            if not r.startswith("ok"):
                bad.append((Path(path).name, r))
    print(len(files), "files")
    for k, v in res.most_common():
        print(f"{v:6} {k}")
    for b in bad[:15]:
        print(" ", *b)
