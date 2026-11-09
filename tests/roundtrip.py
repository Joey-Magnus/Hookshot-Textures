"""Decode a texture, write it back as BC7 (at its own size, or scaled), parse and decode the result, compare."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hstex import bntx, encode, zs  # noqa: E402

ROMFS = "/home/voidm/Games/OcarinaOfTime/romfs"

if __name__ == "__main__":
    scale = int(sys.argv[1])
    for name in sys.argv[2:]:
        src = bntx.parse(zs.decompress(Path(ROMFS, "Tex", name + ".bntx.zs").read_bytes(), ROMFS))
        rgba = bntx.decode_mip0(src)
        if scale != 1:
            rgba = np.asarray(Image.fromarray(rgba).resize((src.width * scale, src.height * scale), Image.LANCZOS))
        out = encode.encode_bc7(src, rgba)
        back = bntx.parse(zs.decompress(zs.compress(out), ROMFS))
        assert bntx.check_layout(back), "layout"
        dec = bntx.decode_mip0(back)
        err = np.abs(dec.astype(int) - rgba.astype(int))
        psnr = 10 * np.log10(255 ** 2 / max(1e-9, float((err[..., :3] ** 2).mean())))
        print(f"{name}: {src.fmt_name} {src.width}x{src.height} -> BC7 {back.width}x{back.height} mips {back.mips} "
              f"srgb {back.srgb} bh {src.bh0}->{back.bh0} psnr {psnr:.1f} dB alpha max err {err[..., 3].max()} "
              f"bytes {len(src.raw)} -> {len(out)}")
