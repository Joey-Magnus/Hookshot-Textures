"""The game's .zs files: zstd frames, most made with one of the dictionaries in Pack/ZsDic.pack.zs (a SARC)."""
from __future__ import annotations

import io
import struct
from functools import lru_cache
from pathlib import Path

import zstandard


def sarc_files(data: bytes) -> dict[str, bytes]:
    data_off = struct.unpack_from("<I", data, 0x0C)[0]
    n = struct.unpack_from("<H", data, 0x1A)[0]
    names = 0x14 + 0x0C + n * 0x10 + 8
    out = {}
    for i in range(n):
        _, attr, s, e = struct.unpack_from("<IIII", data, 0x20 + i * 0x10)
        at = names + (attr & 0xFFFF) * 4
        out[data[at:data.index(b"\0", at)].decode()] = data[data_off + s:data_off + e]
    return out


@lru_cache(maxsize=None)
def dictionaries(romfs: str) -> dict[int, zstandard.ZstdCompressionDict]:
    raw = zstandard.ZstdDecompressor().decompress(Path(romfs, "Pack/ZsDic.pack.zs").read_bytes(),
                                                  max_output_size=1 << 28)
    out = {}
    for d in sarc_files(raw).values():
        zd = zstandard.ZstdCompressionDict(d)
        out[zd.dict_id()] = zd
    return out


def decompress(blob: bytes, romfs: str) -> bytes:
    dict_id = zstandard.get_frame_parameters(blob).dict_id
    d = dictionaries(romfs).get(dict_id) if dict_id else None
    z = zstandard.ZstdDecompressor(dict_data=d) if d else zstandard.ZstdDecompressor()
    return z.stream_reader(io.BytesIO(blob)).read()


def compress(data: bytes, level: int = 16) -> bytes:
    return zstandard.ZstdCompressor(level=level, write_content_size=True).compress(data)
