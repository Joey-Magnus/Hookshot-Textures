"""BNTX textures as the Switch 2 Ocarina of Time ships them (one 2D texture a file, block-linear, "Ounc" platform tag).

Reading gives RGBA8 pixels for mip 0; writing replaces the texture's data in place of the old one, keeping the file's
structure: the same mip count (so the mip pointer array keeps its size), header, strings and relocation table, with
the sizes, offsets and format fields updated.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np
import texture2ddecoder as t2d

GOB_W, GOB_H, GOB_SIZE = 64, 8, 512

# type byte -> (name, block width, block height, bytes per block)
FORMATS = {
    0x0B: ("RGBA8", 1, 1, 4),
    0x0C: ("BGRA8", 1, 1, 4),
    0x1A: ("BC1", 4, 4, 8),
    0x1B: ("BC2", 4, 4, 16),
    0x1C: ("BC3", 4, 4, 16),
    0x1D: ("BC4", 4, 4, 8),
    0x1E: ("BC5", 4, 4, 16),
    0x1F: ("BC6H", 4, 4, 16),
    0x20: ("BC7", 4, 4, 16),
}
for _i, (_w, _h) in enumerate([(4, 4), (5, 4), (5, 5), (6, 5), (6, 6), (8, 5), (8, 6), (8, 8), (10, 5), (10, 6),
                                (10, 8), (10, 10), (12, 10), (12, 12)]):
    FORMATS[0x2D + _i] = (f"ASTC{_w}x{_h}", _w, _h, 16)

VARIANT_SRGB = 0x06


def div_up(a: int, b: int) -> int:
    return (a + b - 1) // b


def block_height_mip0(height_blocks: int) -> int:
    h = height_blocks + height_blocks // 2
    for bh, lim in ((16, 128), (8, 64), (4, 32), (2, 16)):
        if h >= lim:
            return bh
    return 1


def mip_block_height(height_blocks: int, bh: int) -> int:
    while height_blocks <= (bh // 2) * GOB_H and bh > 1:
        bh //= 2
    return bh


def surface_size(width_bytes: int, height_blocks: int, bh: int) -> int:
    return div_up(width_bytes, GOB_W) * div_up(height_blocks, GOB_H * bh) * bh * GOB_SIZE


def _offsets(width_bytes: int, height_blocks: int, bh: int) -> np.ndarray:
    """Byte offset in the block-linear surface of each linear byte (rows of width_bytes, height_blocks rows)."""
    x = np.arange(width_bytes, dtype=np.int64)[None, :]
    y = np.arange(height_blocks, dtype=np.int64)[:, None]
    gobs_per_row = div_up(width_bytes, GOB_W)
    gob = (y // (GOB_H * bh)) * (gobs_per_row * bh * GOB_SIZE) + (x // GOB_W) * (bh * GOB_SIZE) \
        + ((y % (GOB_H * bh)) // GOB_H) * GOB_SIZE
    # (the Switch 2 GOB: bits 5 and 6 hold row bit 1 and column bit 4, the other way round from the Switch 1's)
    inner = (((x & 63) >> 5) << 8) | (((y & 7) >> 2) << 7) | (((x & 31) >> 4) << 6) | (((y >> 1) & 1) << 5) \
        | ((y & 1) << 4) | (x & 15)
    return gob + inner


def unswizzle(data: bytes, width_bytes: int, height_blocks: int, bh: int) -> bytes:
    src = np.frombuffer(data, dtype=np.uint8)
    return src[_offsets(width_bytes, height_blocks, bh)].tobytes()


def swizzle(linear: bytes, width_bytes: int, height_blocks: int, bh: int) -> bytes:
    out = np.zeros(surface_size(width_bytes, height_blocks, bh), dtype=np.uint8)
    out[_offsets(width_bytes, height_blocks, bh)] = np.frombuffer(linear, dtype=np.uint8).reshape(height_blocks,
                                                                                                    width_bytes)
    return out.tobytes()


def mip_layout(width: int, height: int, fmt_type: int, mips: int, bh0: int) -> list[tuple[int, int, int, int, int]]:
    """(offset, size, width_bytes, height_blocks, block height) of each mip, from the start of the data."""
    _, bw, bhgt, bpb = FORMATS[fmt_type]
    out, off = [], 0
    for m in range(mips):
        w, h = max(1, width >> m), max(1, height >> m)
        wb, hb = div_up(w, bw) * bpb, div_up(h, bhgt)
        bh = mip_block_height(hb, bh0)
        size = surface_size(wb, hb, bh)
        out.append((off, size, wb, hb, bh))
        off += size
    return out


@dataclass
class Texture:
    raw: bytearray
    brti: int
    mip_ptrs_at: int
    brtd: int
    rlt: int
    fmt: int
    width: int
    height: int
    depth: int
    layers: int
    mips: int
    bh0: int
    mip_ptrs: list[int]

    @property
    def fmt_type(self) -> int:
        return self.fmt >> 8

    @property
    def srgb(self) -> bool:
        return (self.fmt & 0xFF) == VARIANT_SRGB

    @property
    def fmt_name(self) -> str:
        return FORMATS.get(self.fmt_type, (hex(self.fmt_type),))[0]

    @property
    def data_start(self) -> int:
        return self.brtd + 0x10


def parse(raw: bytes) -> Texture:
    if raw[:4] != b"BNTX":
        raise ValueError("not a BNTX")
    count = struct.unpack_from("<I", raw, 0x24)[0]
    if count != 1:
        raise ValueError(f"{count} textures in one file")
    brti = raw.index(b"BRTI")
    mips = struct.unpack_from("<H", raw, brti + 0x16)[0]
    fmt = struct.unpack_from("<I", raw, brti + 0x1C)[0]
    width, height, depth, layers, layout = struct.unpack_from("<IIIII", raw, brti + 0x24)
    mip_ptrs_at = struct.unpack_from("<Q", raw, brti + 0x70)[0]
    mip_ptrs = list(struct.unpack_from(f"<{mips}Q", raw, mip_ptrs_at))
    brtd = struct.unpack_from("<Q", raw, 0x30)[0]
    rlt = struct.unpack_from("<I", raw, 0x18)[0]
    if raw[brtd:brtd + 4] != b"BRTD" or raw[rlt:rlt + 4] != b"_RLT":
        raise ValueError("unexpected layout")
    return Texture(bytearray(raw), brti, mip_ptrs_at, brtd, rlt, fmt, width, height, depth, layers, mips,
                   1 << (layout & 7), mip_ptrs)


def check_layout(t: Texture) -> bool:
    """Whether the computed mip layout matches the file's mip pointers (validates the tiling math)."""
    lay = mip_layout(t.width, t.height, t.fmt_type, t.mips, t.bh0)
    base = t.mip_ptrs[0]
    return all(base + off == p for (off, *_), p in zip(lay, t.mip_ptrs))


def decode_mip0(t: Texture) -> np.ndarray:
    """Mip 0 as an (h, w, 4) RGBA8 array."""
    name, bw, bhgt, _ = FORMATS[t.fmt_type]
    off, size, wb, hb, bh = mip_layout(t.width, t.height, t.fmt_type, 1, t.bh0)[0]
    data = bytes(t.raw[t.mip_ptrs[0]:t.mip_ptrs[0] + size])
    lin = unswizzle(data, wb, hb, bh)
    pw, ph = div_up(t.width, bw) * bw, div_up(t.height, bhgt) * bhgt
    if name.startswith("ASTC"):
        bgra = t2d.decode_astc(lin, pw, ph, bw, bhgt)
    elif name in ("RGBA8", "BGRA8"):
        a = np.frombuffer(lin, dtype=np.uint8).reshape(ph, pw, 4)
        return (a if name == "RGBA8" else a[..., [2, 1, 0, 3]])[: t.height, : t.width].copy()
    else:
        fn = {"BC1": t2d.decode_bc1, "BC3": t2d.decode_bc3, "BC4": t2d.decode_bc4, "BC5": t2d.decode_bc5,
              "BC7": t2d.decode_bc7}.get(name)
        if fn is None:
            raise ValueError(f"no decoder for {name}")
        bgra = fn(lin, pw, ph)
    a = np.frombuffer(bgra, dtype=np.uint8).reshape(ph, pw, 4)[..., [2, 1, 0, 3]]
    return a[: t.height, : t.width].copy()


def build(t: Texture, width: int, height: int, mip_blocks: list[bytes], fmt_type: int) -> bytes:
    """A new file: t's structure with width x height in fmt_type (the variant, e.g. sRGB, kept). mip_blocks: each
    mip's linear block data (rows of blocks), as many as t.mips."""
    if len(mip_blocks) != t.mips:
        raise ValueError("mip count must stay the same")
    # (the shipped files use either block height 1 or the standard one for their height: keep the same kind)
    bh0 = 1 if t.bh0 == 1 else block_height_mip0(div_up(height, FORMATS[fmt_type][2]))
    lay = mip_layout(width, height, fmt_type, t.mips, bh0)
    data = bytearray(lay[-1][0] + lay[-1][1])
    for (off, size, wb, hb, bh), blocks in zip(lay, mip_blocks):
        data[off:off + size] = swizzle(blocks, wb, hb, bh)

    pre = bytearray(t.raw[: t.data_start])
    rlt_bytes = bytearray(t.raw[t.rlt:])
    pad = t.mip_ptrs[0] - t.data_start   # (the data's own alignment inside BRTD)
    body = bytes(t.raw[t.data_start:t.mip_ptrs[0]]) + bytes(data)
    end = t.data_start + len(body)
    new_rlt = (end + 0xFFF) & ~0xFFF if t.rlt % 0x1000 == 0 else end
    body += bytes(new_rlt - end)
    brtd_size = new_rlt - t.brtd

    b = t.brti
    struct.pack_into("<I", pre, b + 0x1C, (fmt_type << 8) | (t.fmt & 0xFF))
    struct.pack_into("<II", pre, b + 0x24, width, height)
    layout = struct.unpack_from("<I", pre, b + 0x34)[0]
    struct.pack_into("<I", pre, b + 0x34, (layout & ~7) | (bh0.bit_length() - 1))
    struct.pack_into("<I", pre, b + 0x50, len(data))
    struct.pack_into(f"<{t.mips}Q", pre, t.mip_ptrs_at, *[t.mip_ptrs[0] + off for off, *_ in lay])
    struct.pack_into("<Q", pre, t.brtd + 8, brtd_size)
    struct.pack_into("<I", pre, 0x18, new_rlt)
    struct.pack_into("<I", pre, 0x1C, new_rlt + len(rlt_bytes))
    struct.pack_into("<I", rlt_bytes, 4, new_rlt)
    sections = struct.unpack_from("<I", rlt_bytes, 8)[0]
    for s in range(sections):
        at = 0x10 + s * 0x18
        sec_off, sec_size = struct.unpack_from("<II", rlt_bytes, at + 8)
        if sec_off == t.brtd:
            struct.pack_into("<I", rlt_bytes, at + 12, brtd_size)
    assert pad >= 0
    return bytes(pre + body + rlt_bytes)
