"""RGBA8 pictures to BC7 mip chains for bntx.build."""
from __future__ import annotations

import etcpak
import numpy as np
from PIL import Image

from . import bntx


def _to_linear(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255.0


def mip_chain(rgba: np.ndarray, mips: int, srgb: bool) -> list[np.ndarray]:
    """Each level from the full-size picture (Lanczos), colour in linear light when sRGB; alpha stays linear."""
    h, w = rgba.shape[:2]
    out = [rgba]
    base = rgba.astype(np.float32)
    if srgb:
        base[..., :3] = _to_linear(base[..., :3])
    else:
        base /= 255.0
    base[..., 3] = rgba[..., 3] / 255.0
    for m in range(1, mips):
        mw, mh = max(1, w >> m), max(1, h >> m)
        chans = [np.asarray(Image.fromarray(base[..., c], mode="F").resize((mw, mh), Image.LANCZOS)) for c in range(4)]
        lvl = np.stack(chans, axis=-1)
        if srgb:
            lvl[..., :3] = _to_srgb(lvl[..., :3]) / 255.0
        out.append(np.clip(np.rint(lvl * 255.0), 0, 255).astype(np.uint8))
    return out


def bc7_blocks(rgba: np.ndarray) -> bytes:
    """Linear BC7 block rows; the picture is edge-padded to whole 4x4 blocks."""
    h, w = rgba.shape[:2]
    ph, pw = bntx.div_up(h, 4) * 4, bntx.div_up(w, 4) * 4
    if (ph, pw) != (h, w):
        rgba = np.pad(rgba, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    return etcpak.compress_bc7(np.ascontiguousarray(rgba).tobytes(), pw, ph)


def encode_bc7(t: bntx.Texture, rgba: np.ndarray) -> bytes:
    """t with rgba (any size) as BC7, t's mip count and sRGB-ness kept."""
    h, w = rgba.shape[:2]
    levels = mip_chain(rgba, t.mips, t.srgb)
    return bntx.build(t, w, h, [bc7_blocks(l) for l in levels], 0x20)


def bc1_blocks(rgba: np.ndarray) -> bytes:
    """Linear BC1 block rows (opaque, 4-colour blocks only); edge-padded to whole 4x4 blocks."""
    h, w = rgba.shape[:2]
    ph, pw = bntx.div_up(h, 4) * 4, bntx.div_up(w, 4) * 4
    if (ph, pw) != (h, w):
        rgba = np.pad(rgba, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    return etcpak.compress_bc1(np.ascontiguousarray(rgba).tobytes(), pw, ph)


def encode_bc1(t: bntx.Texture, rgba: np.ndarray) -> bytes:
    """t with an OPAQUE rgba (any size) as BC1: half of BC7's 8 bits a pixel. Only for pictures without alpha: BC1's
    one transparent colour is not used, so a cut-out would come out opaque."""
    h, w = rgba.shape[:2]
    levels = mip_chain(rgba, t.mips, t.srgb)
    return bntx.build(t, w, h, [bc1_blocks(l) for l in levels], 0x1A)
