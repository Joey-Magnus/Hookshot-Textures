"""A pack sized to the game's texture heap, built from a full 2x pack.

The full 2x pack grows the textures it replaces from ~1.6 GB to ~15 GB (4x the pixels, and BC7's 8 bits a pixel against the
originals' ASTC at ~2-3): far past the game's TextureHeap (2.34 GB, System/HeapSize/...HeapDef), so the game keeps
compacting and re-streaming textures, and Hookshot's submit-time capture copies every page it rewrites. This keeps 2x only
for originals up to `max_orig` pixels (the small and medium textures: the most visible gain for the least memory), as BC1
when the picture is opaque (4 bits a pixel), and leaves the large ones as the game's own (not in the pack).

Each kept texture is made from what is at hand, never by a paid model:
- opaque: the full pack's 2x picture, re-encoded as BC1;
- alpha, and the full pack has it right: that file as it is;
- BC1 originals with punch-through alpha (cut-outs; the old decoder lost them and the full pack drew them black): the
  original decoded again (bntx.decode_mip0 now keeps BC1's alpha), its RGB upscale taken from the cache (Topaz, then
  Upscayl; Upscayl run locally if neither has it), BC7.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import bntx, encode, fal, upscayl, zs

CACHE_MODELS = ("topaz-std", "upscayl-ultrasharp")


@dataclass
class Result:
    name: str
    action: str   # "skip-large", "bc1", "copy", "rebuild", "skip-missing"
    orig_bytes: int = 0
    new_bytes: int = 0


def cached_upscale2x(rgba: np.ndarray) -> np.ndarray:
    """fal.upscale2x from whichever model's cache has this picture; Upscayl (local, free) when none does."""
    h, w = rgba.shape[:2]
    ph, pw = max(1, int(h * fal.PAD)), max(1, int(w * fal.PAD))
    rgb = np.pad(rgba[..., :3], ((ph, ph), (pw, pw), (0, 0)), mode="wrap")
    key = hashlib.sha256(fal._png(np.ascontiguousarray(rgb))).hexdigest() + ".png"
    for model in CACHE_MODELS:
        if (fal.CACHE / model / key).exists():
            return fal.upscale2x(rgba, model, None)
    return fal.upscale2x(rgba, "upscayl-ultrasharp", None)


def build_one(name: str, romfs: str, full_tex: Path, out_tex: Path, max_orig: int, zstd: int) -> Result:
    orig_raw = zs.decompress(Path(romfs, "Tex", name).read_bytes(), romfs)
    t = bntx.parse(orig_raw)
    if max(t.width, t.height) > max_orig:
        return Result(name, "skip-large")
    full = full_tex / name
    if not full.exists():
        return Result(name, "skip-missing")
    orig_rgba = bntx.decode_mip0(t)
    punch = t.fmt_name == "BC1" and int(orig_rgba[..., 3].min()) < 250
    dst = out_tex / name
    if punch:
        data = zs.compress(encode.encode_bc7(t, cached_upscale2x(orig_rgba)), level=zstd)
        action = "rebuild"
    else:
        full_raw = zs.decompress(full.read_bytes(), romfs)
        up = bntx.decode_mip0(bntx.parse(full_raw))
        if int(up[..., 3].min()) < 250:
            shutil.copyfile(full, dst)
            return Result(name, "copy", len(orig_raw), len(full_raw))
        data = zs.compress(encode.encode_bc1(t, up), level=zstd)
        action = "bc1"
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)
    return Result(name, action, len(orig_raw), zs.content_size(data[:32]))
