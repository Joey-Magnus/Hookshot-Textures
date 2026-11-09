"""A test mod: every Alb texture whose name matches a pattern, tinted magenta and written back as BC7 at its own size.
Shows in a frame whether the game loads rewritten files (dictionary-less zstd, BC7 in place of ASTC, new sizes)."""
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hstex import bntx, encode, zs  # noqa: E402

ROMFS = "/home/voidm/Games/OcarinaOfTime/romfs"


def one(args):
    src_path, out_dir, scale = args
    t = bntx.parse(zs.decompress(Path(src_path).read_bytes(), ROMFS))
    if t.layers != 1 or t.depth != 1:
        return None
    rgba = bntx.decode_mip0(t).copy()
    rgba[..., 0] = np.maximum(rgba[..., 0], 220)
    rgba[..., 1] //= 4
    rgba[..., 2] = np.maximum(rgba[..., 2], 200)
    if scale != 1:
        rgba = np.asarray(Image.fromarray(rgba).resize((t.width * scale, t.height * scale), Image.LANCZOS))
    out = Path(out_dir, "romfs/Tex", Path(src_path).name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(zs.compress(encode.encode_bc7(t, rgba), level=3))
    return out.name


if __name__ == "__main__":
    pattern, out_dir, scale = re.compile(sys.argv[1], re.I), sys.argv[2], int(sys.argv[3])
    files = [str(p) for p in sorted(Path(ROMFS, "Tex").glob("*_Alb*.bntx.zs")) if pattern.search(p.name)]
    with ProcessPoolExecutor() as ex:
        done = [r for r in ex.map(one, [(f, out_dir, scale) for f in files]) if r]
    print(len(done), "textures written to", out_dir)
